import os
import sys
import subprocess
import time
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
        console.info(f"Removing NRPT rules for domains: {domains}")
        subprocess.run(ps_command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def is_enabled(self) -> bool:
        process_name = "openconnect.exe"
        for process in psutil.process_iter(attrs=["name"]):
            if process.info["name"] == process_name:
                return True
        return False

    def connect(self, creds: Dict[str, Any], vpn_name: str, no_split: bool, progress_callback: Optional[callable] = None) -> Union[bool, str, None]:
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
        org_config = organizations.get(vpn_name, {})
        domain = org_config.get("domain")
        iprange = org_config.get("ip")
        if domain: env_vars["VPN_DOMAIN"] = domain
        if iprange:
            env_vars.update({
                "CISCO_SPLIT_INC": "2",
                "CISCO_SPLIT_INC_1_ADDR": iprange if isinstance(iprange, str) else " ".join(iprange),
                "CISCO_SPLIT_INC_1_MASK": "255.255.0.0",
                "CISCO_SPLIT_INC_1_MASKLEN": "16",
            })

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
        
        if auth_method == "cert":
            # Use cert from YAML or default path
            cert_path = org_config.get("cert") or creds.get("cert_path")
            if not cert_path:
                cert_path = "~/.ssh/uva/decrypted_user.pem"
            
            if not os.path.exists(path_expand(cert_path)):
                console.error(f"Certificate file not found at {cert_path}")
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
        try:
            proc = subprocess.Popen(
                cmd_list, 
                stdin=subprocess.PIPE, 
                start_new_session=True, 
                env=env_vars,
                text=True
            )
            
            if auth_method != "cert":
                pw = creds.get("pw")
                if pw:
                    proc.stdin.write(pw + "\n")
                    proc.stdin.flush()
            
            time.sleep(2)
            
            # Track the actual openconnect PID
            for p in psutil.process_iter(['pid', 'name']):
                if p.info['name'] == 'openconnect.exe':
                    self._pid = p.info['pid']
            
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