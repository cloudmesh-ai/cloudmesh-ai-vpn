import os
import subprocess
import time
import sys
import psutil
from typing import Any, Dict, List, Union, Optional

from cloudmesh.ai.common.io import console
from cloudmesh.ai.common.io import path_expand
from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.vpn.organizations import organizations


class MacOpenConnectKeychainStrategy(VpnOSStrategy):
    def __init__(self, vpn_context: "Vpn"):
        super().__init__(vpn_context)
        self._pid = None

    def _discover_openconnect(self) -> Optional[str]:
        return self._discover_binary(
            "openconnect",
            [
                "/usr/bin/openconnect",
                "/usr/local/bin/openconnect",
                "/opt/homebrew/bin/openconnect",
            ],
        )

    def _discover_anyconnect(self) -> Optional[str]:
        return None

    def _discover_vpn_slice(self) -> Optional[str]:
        path = self._discover_binary(
            "vpn-slice", ["/usr/local/bin/vpn-slice", "/opt/homebrew/bin/vpn-slice"]
        )
        if path and "shims" in path:
            try:
                actual_path = subprocess.check_output(
                    ["pyenv", "which", "vpn-slice"], text=True
                ).strip()
                return actual_path
            except Exception:
                return path
        return path

    @property
    def vpn_slice(self) -> Optional[str]:
        return self._discover_vpn_slice()

    def is_enabled(self) -> bool:
        for proc in psutil.process_iter(attrs=["name"]):
            if proc.info["name"] == "openconnect":
                return True
        return False

    def connect(
        self, creds: Dict[str, Any], vpn_name: str, no_split: bool, progress_callback: Optional[callable] = None
    ) -> Union[bool, str, None]:
        if progress_callback:
            progress_callback("Checking dependencies...")
        oc_exe = self.openconnect
        if not oc_exe:
            console.error(
                "OpenConnect binary not found. Please install it via Homebrew: brew install openconnect"
            )
            return False

        vs_exe = self.vpn_slice
        if not vs_exe and not no_split:
            console.error(
                "vpn-slice binary not found. Please install it: brew install vpn-slice"
            )
            return False

        host = organizations[vpn_name]["host"]
        if progress_callback:
            progress_callback("Warming up sudo...")
        # Warm up sudo to cache the system password
        from cloudmesh.ai.common.sudo import Sudo
        if not Sudo.password():
            return False

        script_arg = ""
        if not no_split:
            org_config = organizations.get(vpn_name, {})
            ip_range = org_config.get("ip")
            if isinstance(ip_range, list):
                slice_target = " ".join(ip_range)
            else:
                slice_target = ip_range if ip_range else host
            script_arg = f"--script='{vs_exe} -v {slice_target}'"

        user_val = creds.get("user")
        if not isinstance(user_val, str):
            org_config = organizations.get(vpn_name, {})
            user_val = org_config.get("username") or org_config.get("user")

        if not isinstance(user_val, str):
            import getpass

            user = getpass.getuser()
        else:
            user = user_val

        cert_path = creds.get("cert_path")
        if not cert_path:
            default_cert = os.path.expanduser("~/.ssh/uva/user.crt")
            if os.path.exists(default_cert):
                cert_path = default_cert

        key_path = creds.get("key_path")
        if not key_path:
            default_key = os.path.expanduser("~/.ssh/uva/user.key")
            if os.path.exists(default_key):
                key_path = default_key

        if not cert_path or not key_path:
            console.error(
                "cert_path and key_path are required for openconnect-keychain provider (defaults ~/.ssh/uva/user.crt and user.key not found)"
            )
            return False

        keychain_service = creds.get("keychain_service", "uva-key-pass")
        try:
            console.msg(f"Searching Keychain for service: {keychain_service}...")
            # Added -a uva to match the required account field for add-generic-password
            passphrase = subprocess.check_output(
                [
                    "security",
                    "find-generic-password",
                    "-w",
                    "-a",
                    "uva",
                    "-s",
                    keychain_service,
                ],
                text=True,
                stderr=subprocess.STDOUT,
            ).strip()
        except subprocess.CalledProcessError as e:
            console.error(f"Keychain lookup failed for '{keychain_service}'")
            # e.output is already a string because text=True was used in check_output
            output = e.output.strip() if e.output else "No output"
            console.error(f"Shell output: {output}")
            console.msg(
                f"To add it securely (you will be prompted for the password), run:"
            )
            console.msg(
                f"  security add-generic-password -a uva -s {keychain_service}"
            )
            return False

        if progress_callback:
            progress_callback("Launching OpenConnect (Keychain)...")
        # Use standard sudo since password is now cached via sudo -v
        # We remove the invalid --passphrase-from-fsid flag.
        command = f"sudo {oc_exe} --protocol=anyconnect -u {user} -c {path_expand(cert_path)} -k {path_expand(key_path)} {script_arg} {host}"
        console.msg(f"Connecting via OpenConnect (Keychain): {command}")

        try:
            # Construct the command as a list to avoid shell=True and TTY issues with sudo.
            cmd_list = [
                "sudo",
                oc_exe,
                "--protocol=anyconnect",
                "-u",
                user,
                "-c",
                path_expand(cert_path),
                "-k",
                path_expand(key_path),
            ]
            if script_arg:
                vs_exe_path = self.vpn_slice
                org_config = organizations.get(vpn_name, {})
                ip_range = org_config.get("ip")
                if isinstance(ip_range, list):
                    slice_target = " ".join(ip_range)
                else:
                    slice_target = ip_range if ip_range else host
                cmd_list.extend(["--script", f"{vs_exe_path} -v {slice_target}"])

            cmd_list.append(host)

            # Use subprocess.Popen with stdin=PIPE to provide the passphrase.
            proc = subprocess.Popen(
                cmd_list,
                stdin=subprocess.PIPE,
                stdout=None,  # Inherit stdout
                stderr=None,  # Inherit stderr
                text=True,
            )

            # Move the process to its own process group so it doesn't receive SIGHUP when the parent exits.
            try:
                os.setpgid(proc.pid, 0)
            except (ProcessLookupError, PermissionError):
                pass  # Ignore if we can't set pgid (e.g. due to sudo privilege change)

            # Provide the passphrase retrieved from the Keychain.
            if passphrase:
                proc.stdin.write(passphrase + "\n")
                proc.stdin.flush()

            # Give it a few seconds to start and establish connection
            time.sleep(2)

            # Find the PID of the actual openconnect process
            for p in psutil.process_iter(["pid", "name"]):
                if p.info["name"] == "openconnect":
                    self._pid = p.info["pid"]
                    break

            if self._pid:
                return True
            else:
                console.error("OpenConnect process not found after starting.")
                return False

        except Exception as e:
            console.error(f"Connection failed: {e}")
            return False

    def watch(self) -> List[str]:
        evidence = []
        
        # Single pass over processes to find all relevant PIDs
        vpn_slice_pids = []
        openconnect_pids = []
        cisco_pids = []
        
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                name = proc.info["name"] or ""
                if "vpn-slice" in name:
                    vpn_slice_pids.append(str(proc.info["pid"]))
                elif "openconnect" in name:
                    openconnect_pids.append(str(proc.info["pid"]))
                elif "vpnagentd" in name or "Cisco Secure Client" in name:
                    cisco_pids.append(str(proc.info["pid"]))
        except Exception:
            pass

        # 1. vpn-slice status
        if vpn_slice_pids:
            evidence.append(f"[Process] 'vpn-slice' is running (PIDs: {', '.join(vpn_slice_pids)})")
        else:
            evidence.append("[Process] 'vpn-slice' is NOT running")

        # 2. openconnect status
        if openconnect_pids:
            evidence.append(f"[Process] 'openconnect' is running (PIDs: {', '.join(openconnect_pids)})")
            # Only run expensive ps aux if openconnect is actually running
            try:
                import re
                out = subprocess.check_output(["ps", "aux"], text=True)
                for line in out.splitlines():
                    if "vpn-slice" in line:
                        routes = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?", line)
                        if routes:
                            # Filter out the binary path
                            filtered_routes = [r for r in routes if r not in line.split("/bin/")[0]]
                            evidence.append(f"[OpenConnect] Routes configured via vpn-slice: {', '.join(filtered_routes)}")
                        else:
                            evidence.append("[OpenConnect] Running with vpn-slice but no routes detected in command line")
                        break
            except Exception:
                pass
        else:
            evidence.append("[Process] 'openconnect' is NOT running")

        # 3. Cisco VPN status
        if cisco_pids:
            evidence.append(f"[Process] 'Cisco VPN' is running (PIDs: {', '.join(cisco_pids)})")
        else:
            evidence.append("[Process] 'Cisco VPN' is NOT running")

        # 4. Routing table check
        current_org = self.get_current_org()
        org_name = current_org.lower() if current_org else self.vpn.service_key.lower()
        ip_range = organizations.get(org_name, {}).get("ip")
        
        if ip_range:
            targets = ip_range if isinstance(ip_range, list) else [ip_range]
            try:
                import re
                # Call netstat once per watch cycle instead of once per target
                route_out = subprocess.check_output(["netstat", "-rn"], text=True)
                for target in targets:
                    search_ip = target.split("/")[0].strip()
                    if re.search(rf"^\s*{re.escape(search_ip)}(\s+|/)", route_out, re.MULTILINE):
                        display_net = target if "/" in target else f"{target}/16"
                        evidence.append(f"[Routing Table] Route to {display_net} found in system routing table (netstat -rn) (Org: {org_name})")
            except Exception:
                pass

        return evidence

    def disconnect(self) -> None:
        console.msg("Disconnecting OpenConnect...")
        if self._pid:
            try:
                console.msg(f"Sending SIGINT to OpenConnect process {self._pid}")
                os.kill(self._pid, 2)  # SIGINT
                time.sleep(2)
                if psutil.pid_exists(self._pid):
                    console.warning(
                        f"Process {self._pid} still exists, forcing termination"
                    )
                    os.kill(self._pid, 15)  # SIGTERM
            except ProcessLookupError:
                pass
            except Exception as e:
                console.error(f"Error during targeted disconnect: {e}")
        else:
            from cloudmesh.ai.common.Shell import Shell

            Shell.run("sudo pkill -SIGINT openconnect")

        from cloudmesh.ai.common.Shell import Shell

        try:
            Shell.run("sudo pkill vpn-slice")
        except Exception:
            pass  # Ignore if vpn-slice is already gone

    def get_reset_commands(self, service: Optional[str] = None) -> List[str]:
        commands = []
        target_orgs = [service.lower()] if service else list(organizations.keys())

        for org in target_orgs:
            ip_range = organizations.get(org, {}).get("ip")
            if ip_range:
                targets = ip_range if isinstance(ip_range, list) else [ip_range]
                for target in targets:
                    commands.append(f"sudo route delete -net {target}")
        return commands

    def reset_routes(self, service: Optional[str] = None) -> bool:
        # 1. Kill processes first, otherwise they will just re-add the routes
        self.disconnect()

        commands = self.get_reset_commands(service)
        if not commands:
            return True

        success = True
        for cmd in commands:
            # Try deleting as a network first, then as a host if it fails
            target = cmd.split()[-1]

            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if res.returncode != 0 and "not found" not in res.stderr.lower():
                    # Try without -net (as a host route)
                    host_cmd = f"sudo route delete {target}"
                    res_host = subprocess.run(
                        host_cmd, shell=True, capture_output=True, text=True
                    )
                    if (
                        res_host.returncode != 0
                        and "not found" not in res_host.stderr.lower()
                    ):
                        console.error(
                            f"Failed to remove route {target}: {res_host.stderr.strip()}"
                        )
                        success = False
            except Exception as e:
                console.error(f"Exception while removing route {target}: {e}")
                success = False
        return success