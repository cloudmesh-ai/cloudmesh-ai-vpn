import os
import sys
import subprocess
import time
import re
import psutil
from typing import Any, Dict, List, Union, Optional

from cloudmesh.ai.common.io import console
from cloudmesh.ai.common.sys import os_is_windows
from cloudmesh.ai.vpn.vpn import VpnDependencyError
from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.vpn.organizations import organizations
from cloudmesh.ai.vpn.windows import win_install, ensure_choco_bin_on_process_path, get_openconnect_exe

def path_expand(path):
    return os.path.expanduser(path)


def _normalize_cert_path(value: Any) -> Optional[str]:
    if isinstance(value, list):
        return value[0] if value else None
    if isinstance(value, str):
        return value
    return None


def _extract_cert_uri(system_keys_output: str, match_terms: List[str]) -> Optional[str]:
    lines = system_keys_output.splitlines()
    normalized_terms = [term.lower() for term in match_terms if isinstance(term, str) and term.strip()]

    if not normalized_terms:
        return None

    current_cert_uri = None
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("Cert URI: "):
            current_cert_uri = stripped_line.split("Cert URI: ", 1)[1].strip() or None
            continue
        if stripped_line.startswith("Object Label:"):
            continue

        line_lower = line.lower()
        if not any(term in line_lower for term in normalized_terms):
            continue
        if current_cert_uri:
            return current_cert_uri

    return None


def _cidr_to_route_parts(cidr: str) -> Optional[tuple[str, str, str]]:
    if "/" not in cidr:
        return None

    network, prefix = cidr.split("/", 1)
    try:
        prefix_len = int(prefix)
    except ValueError:
        return None

    if prefix_len < 0 or prefix_len > 32:
        return None

    mask_bits = ("1" * prefix_len).ljust(32, "0")
    octets = [str(int(mask_bits[i:i + 8], 2)) for i in range(0, 32, 8)]
    return network, ".".join(octets), str(prefix_len)


class WindowsVpnStrategy(VpnOSStrategy):
    def __init__(self, vpn_context: 'Vpn'):
        super().__init__(vpn_context)
        self._pid = None

    def _discover_openconnect(self) -> Optional[str]:
        # Windows specific discovery
        return get_openconnect_exe()

    def _discover_anyconnect(self) -> Optional[str]:
        system_drive = os.environ.get("SYSTEMDRIVE", "C:")
        return self._discover_binary("vpncli.exe", [
            rf"{system_drive}\Program Files (x86)\Cisco\Cisco Secure Client\vpncli.exe",
            rf"{system_drive}\Program Files (x86)\Cisco\Cisco AnyConnect Secure Mobility Client\vpncli.exe",
        ])

    def _stop_vpn_services(self) -> None:
        if self.vpn.verbosity >= 1:
            console.warning("Restarting vpnagent to avoid conflict")
        for program in ["vpnagent.exe", "vpncli.exe"]:
            subprocess.run(
                ["taskkill", "/im", program, "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        try:
            from cloudmesh.ai.common.Shell import Shell
            Shell.run("net stop csc_vpnagent")
        except Exception:
            pass
        try:
            from cloudmesh.ai.common.Shell import Shell
            Shell.run("net start csc_vpnagent")
        except Exception:
            pass
        subprocess.run(
            ["taskkill", "/im", "csc_ui.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    def _remove_nrpt_rules(self) -> None:
        domains = [f".{org['domain']}" for org in organizations.values() if "domain" in org]
        if not domains:
            return
        conditions = " -or ".join(f"( $_.Namespace -eq '{d}' )" for d in domains)
        ps_command = (
            "powershell.exe -Command "
            f'"Get-DnsClientNrptRule | '
            f"Where-Object {{ {conditions} }} | "
            f'Remove-DnsClientNrptRule -Force"'
        )
        if self.vpn.verbosity >= 1:
            console.info(f"Removing NRPT rules for domains: {domains}")
        subprocess.run(ps_command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def is_enabled(self) -> bool:
        process_name = "openconnect.exe"
        for process in psutil.process_iter(attrs=["name"]):
            if process.info["name"] == process_name:
                return True
        return False

    def _route_exists(self, cidr: str) -> bool:
        parsed = _cidr_to_route_parts(cidr)
        if not parsed:
            return False

        network, mask, _ = parsed
        try:
            result = subprocess.run(
                ["route", "print", network],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return False

        route_pattern = rf"\b{re.escape(network)}\s+{re.escape(mask)}\b"
        return bool(re.search(route_pattern, result.stdout))

    def _nrpt_rule_exists(self, domain: str) -> bool:
        if not domain:
            return False

        ps_command = (
            "Get-DnsClientNrptRule | "
            f"Where-Object {{ $_.Namespace -eq '.{domain}' }} | "
            "Select-Object -First 1 -ExpandProperty Namespace"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-Command", ps_command],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return False

        return result.returncode == 0 and f".{domain}" in (result.stdout or "")

    def _wait_for_split_tunnel_ready(self, proc: subprocess.Popen, domain: Optional[str], routes: List[str], timeout: int = 25) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                return False

            dns_ready = True
            if domain:
                dns_ready = self._nrpt_rule_exists(domain)

            route_ready = True
            for route in routes:
                if isinstance(route, str) and "/" in route:
                    if self._route_exists(route):
                        route_ready = True
                        break
                    route_ready = False

            if dns_ready and route_ready:
                return True

            time.sleep(1)

        return proc.poll() is None

    def _get_system_cert_uri(self, org_config: Dict[str, Any]) -> Optional[str]:
        if not os_is_windows():
            return None

        try:
            from cloudmesh.ai.common.Shell import Shell
            system_keys = Shell.run("list-system-keys")
        except Exception:
            return None

        match_terms = []
        connection_check = org_config.get("connection_check")
        if isinstance(connection_check, list):
            match_terms.extend(item for item in connection_check if isinstance(item, str))

        org_name = org_config.get("name")
        if isinstance(org_name, str):
            match_terms.append(org_name)

        domain = org_config.get("domain")
        if isinstance(domain, str):
            match_terms.append(domain)

        return _extract_cert_uri(system_keys, match_terms)

    def connect(self, creds: Dict[str, Any], vpn_name: str, no_split: bool, progress_callback: Optional[callable] = None) -> Union[bool, str, None]:
        self._pid = None
        if progress_callback:
            progress_callback("Checking administrator privileges...")
        import pyuac
        if not pyuac.isUserAdmin():
            console.error("Please run your terminal as administrator")
            sys.exit(1)

        if progress_callback:
            progress_callback("Verifying dependencies...")
        ensure_choco_bin_on_process_path()
        
        oc_exe = self.openconnect or get_openconnect_exe() or win_install()
        self._openconnect = oc_exe

        if not oc_exe or not os.path.exists(oc_exe):
            console.error(f"VPN binary not found. Please install OpenConnect.")
            return False

        script_location = os.path.join(os.path.dirname(__file__), "..", "bin", "split-script-win.js")
        
        env_vars = os.environ.copy()
        # Pass log level to the JS script (0=ERROR, 1=INFO, 2=DEBUG, 3=TRACE)
        # JS script expects: ERROR=0, INFO=1, DEBUG=2, TRACE=3
        env_vars["LOG_LEVEL"] = str(min(self.vpn.verbosity, 3))
        org_config = organizations.get(vpn_name, {})
        domain = org_config.get("domain")
        iprange = org_config.get("ip")
        if domain: env_vars["VPN_DOMAIN"] = domain
        if iprange:
            routes = [iprange] if isinstance(iprange, str) else list(iprange)
            route_index = 0
            for route in routes:
                if not isinstance(route, str):
                    continue

                route = route.strip()
                parsed = _cidr_to_route_parts(route)
                if not parsed:
                    continue

                network, mask, prefix_len = parsed
                env_vars[f"EXTRA_SPLIT_INC_{route_index}_ADDR"] = network
                env_vars[f"EXTRA_SPLIT_INC_{route_index}_MASK"] = mask
                env_vars[f"EXTRA_SPLIT_INC_{route_index}_MASKLEN"] = prefix_len
                route_index += 1

            if route_index:
                env_vars["EXTRA_SPLIT_INC_COUNT"] = str(route_index)
        else:
            routes = []

        # Determine User
        user_val = creds.get('user')
        if not isinstance(user_val, str):
            user_val = org_config.get('username') or org_config.get('user')
        
        if not isinstance(user_val, str):
            import getpass
            user = getpass.getuser()
        else:
            user = user_val

        # Determine Auth Method (Cert vs PW)
        auth_method = org_config.get("auth", "cert")
        
        cmd_list = [oc_exe, org_config.get("host"), f'--user={user}']
        if self.vpn.verbosity == 0:
            cmd_list.append("-q")
        
        if auth_method == "cert":
            cert_uri = self._get_system_cert_uri(org_config)
            if cert_uri:
                if self.vpn.verbosity >= 1:
                    console.info("Using certificate from Windows system key store")
                cmd_list.extend(["--certificate", cert_uri])
            else:
                # Fall back to file-based certificate handling.
                cert_path = _normalize_cert_path(org_config.get("cert")) or _normalize_cert_path(
                    creds.get("cert_path")
                )
                if not cert_path:
                    cert_path = "~/.ssh/uva/decrypted_user.pem"

                if not os.path.exists(path_expand(cert_path)):
                    console.error(
                        f"Certificate file not found at {cert_path}, and no matching Windows system certificate was found"
                    )
                    return False

                cmd_list.extend(["--certificate", path_expand(cert_path)])
        else:
            # Password auth
            pw = creds.get("pw")
            if pw:
                cmd_list.append("--passwd-on-stdin")

        if not no_split:
            cmd_list.append(f"--script={script_location}")

        if progress_callback:
            progress_callback("Stopping conflicting VPN services...")
        # Stop conflicting services before starting
        self._stop_vpn_services()
        
        if progress_callback:
            progress_callback("Launching OpenConnect...")
        if self.vpn.verbosity >= 1:
            console.info(f"Connecting via OpenConnect: {' '.join(cmd_list)}")

        try:
            # Adjust output based on verbosity:
            # 0: Hidden
            # 1: Raw (shown to console)
            # 2+: Prefixed/Captured
            verbosity = self.vpn.verbosity
            if verbosity == 0:
                stdout_val = subprocess.DEVNULL
                stderr_val = subprocess.DEVNULL
            elif verbosity == 1:
                stdout_val = None
                stderr_val = None
            else: # verbosity >= 2
                stdout_val = subprocess.PIPE
                stderr_val = subprocess.PIPE

            proc = subprocess.Popen(
                cmd_list, 
                stdin=subprocess.PIPE, 
                stdout=stdout_val,
                stderr=stderr_val,
                start_new_session=True, 
                env=env_vars,
                text=True
            )

            if verbosity >= 2:
                import threading
                def stream_output(pipe, prefix):
                    for line in iter(pipe.readline, ""):
                        console.print(f"{prefix} {line.strip()}")
                
                threading.Thread(target=stream_output, args=(proc.stdout, "[OpenConnect-Out]"), daemon=True).start()
                threading.Thread(target=stream_output, args=(proc.stderr, "[OpenConnect-Err]"), daemon=True).start()
            
            if auth_method != "cert":
                pw = creds.get("pw")
                if pw:
                    proc.stdin.write(pw + "\n")
                    proc.stdin.flush()
            
            time.sleep(2)

            if proc.poll() is not None:
                console.error(f"OpenConnect exited during startup with exit code {proc.returncode}.")
                return False

            self._pid = proc.pid

            if not no_split:
                if not self._wait_for_split_tunnel_ready(proc, domain, routes):
                    if proc.poll() is not None:
                        console.error(f"OpenConnect exited before split DNS/routes were ready with exit code {proc.returncode}.")
                        return False
                    console.warning("OpenConnect started, but split DNS/routes were not fully ready before timeout.")
            return True
                
        except Exception as e:
            console.error(f"Connection failed: {e}")
            return False

    def watch(self) -> List[str]:
        evidence = []
        openconnect_pids = []
        
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                if proc.info["name"] == "openconnect.exe":
                    openconnect_pids.append(str(proc.info["pid"]))
        except Exception:
            pass

        if openconnect_pids:
            evidence.append(f"[Process] 'openconnect.exe' is running (PIDs: {', '.join(openconnect_pids)})")
        else:
            evidence.append("[Process] 'openconnect.exe' is NOT running")

        return evidence

    def check_dependencies(self, choco: bool = False) -> None:
        """Check if required binaries are installed, and attempt installation if requested."""
        try:
            subprocess.run(
                ["openconnect", "-V"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            if not choco:
                raise VpnDependencyError(
                    "OpenConnect not found. Please install, or use --choco parameter."
                )
            else:
                from cloudmesh.ai.vpn.windows import win_install
                console.warning("OpenConnect not found. Installing OpenConnect...")
                win_install()

    def disconnect(self) -> None:
        if self.vpn.verbosity >= 1:
            console.info("Disconnecting OpenConnect...")
        if self._pid:
            try:
                p = psutil.Process(self._pid)
                p.terminate()
                try:
                    p.wait(timeout=3)
                except psutil.TimeoutExpired:
                    p.kill()
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                console.error(f"Error during targeted disconnect: {e}")
        else:
            for process in psutil.process_iter(attrs=["name"]):
                if process.info["name"] == "openconnect.exe":
                    try:
                        process.terminate()
                    except Exception:
                        pass
        
        self._remove_nrpt_rules()

    def get_reset_commands(self, service: Optional[str] = None) -> List[str]:
        # Windows uses NRPT rules and the JS script for routing
        # The primary cleanup is removing NRPT rules
        return ["self._remove_nrpt_rules()"]

    def reset_routes(self, service: Optional[str] = None) -> bool:
        self.disconnect()
        self._remove_nrpt_rules()
        return True
