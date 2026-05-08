import os
import subprocess
import time
import sys
import psutil
from typing import Any, Dict, List, Union, Optional

from cloudmesh.ai.common.io import console
from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.vpn.organizations import organizations

def path_expand(path):
    return os.path.expanduser(path)

class MacVpnStrategy(VpnOSStrategy):
    def __init__(self, vpn_context: 'Vpn'):
        super().__init__(vpn_context)
        self._pid = None

    def _discover_openconnect(self) -> Optional[str]:
        return self._discover_binary("openconnect", ["/usr/bin/openconnect", "/usr/local/bin/openconnect", "/opt/homebrew/bin/openconnect"])

    def _discover_vpn_slice(self) -> Optional[str]:
        path = self._discover_binary("vpn-slice", ["/usr/local/bin/vpn-slice", "/opt/homebrew/bin/vpn-slice"])
        if path and "shims" in path:
            try:
                actual_path = subprocess.check_output(["pyenv", "which", "vpn-slice"], text=True).strip()
                return actual_path
            except Exception:
                return path
        return path

    @property
    def vpn_slice(self) -> Optional[str]:
        return self._discover_vpn_slice()

    def is_enabled(self) -> bool:
        for proc in psutil.process_iter(attrs=["name"]):
            if proc.info["name"] == "openconnect": return True
        return False

    def connect(self, creds: Dict[str, Any], vpn_name: str, no_split: bool) -> Union[bool, str, None]:
        oc_exe = self.openconnect
        if not oc_exe:
            console.error("OpenConnect binary not found. Please install it via Homebrew: brew install openconnect")
            return False
        
        vs_exe = self.vpn_slice
        if not vs_exe and not no_split:
            console.error("vpn-slice binary not found. Please install it: brew install vpn-slice")
            return False

        host = organizations[vpn_name]["host"]
        
        # Warm up sudo to cache the system password
        from cloudmesh.ai.common.sudo import Sudo
        if not Sudo.password():
            return False

        # Handle Routing Script
        script_arg = ""
        if not no_split:
            org_config = organizations.get(vpn_name, {})
            ip_range = org_config.get("ip")
            if isinstance(ip_range, list):
                slice_target = " ".join(ip_range)
            else:
                slice_target = ip_range if ip_range else host
            script_arg = f"{vs_exe} -v {slice_target}"

        # Determine User
        user_val = creds.get('user')
        if not isinstance(user_val, str):
            org_config = organizations.get(vpn_name, {})
            user_val = org_config.get('username') or org_config.get('user')
        
        if not isinstance(user_val, str):
            import getpass
            user = getpass.getuser()
        else:
            user = user_val

        # Determine Auth Method (Cert vs PW)
        org_config = organizations.get(vpn_name, {})
        auth_method = org_config.get("auth", "cert")
        
        cmd_list = ["sudo", oc_exe, "--protocol=anyconnect", "-u", user]
        
        if auth_method == "cert":
            # Use cert from YAML or default path
            cert_path = org_config.get("cert") or creds.get("cert_path")
            if not cert_path:
                cert_path = "~/.ssh/uva/decrypted_user.pem"
            
            if not os.path.exists(path_expand(cert_path)):
                console.error(f"Certificate file not found at {cert_path}")
                return False
            
            cmd_list.extend(["-c", path_expand(cert_path)])
        else:
            # Password auth
            pw = creds.get("pw")
            if pw:
                cmd_list.append("--passwd-on-stdin")

        if script_arg:
            cmd_list.extend(["--script", script_arg])
        
        cmd_list.append(host)
        
        try:
            proc = subprocess.Popen(
                cmd_list,
                stdin=subprocess.PIPE,
                stdout=None,
                stderr=None,
                text=True
            )
            
            # Move the process to its own process group for persistence
            try:
                os.setpgid(proc.pid, 0)
            except (ProcessLookupError, PermissionError):
                pass 
            
            if auth_method != "cert":
                pw = creds.get("pw")
                if pw:
                    proc.stdin.write(pw + "\n")
                    proc.stdin.flush()
            
            time.sleep(2)
            
            # Track the actual openconnect PID
            for p in psutil.process_iter(['pid', 'name']):
                if p.info['name'] == 'openconnect':
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
        vpn_slice_pids = []
        openconnect_pids = []
        
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                name = proc.info["name"] or ""
                if "vpn-slice" in name:
                    vpn_slice_pids.append(str(proc.info["pid"]))
                elif "openconnect" in name:
                    openconnect_pids.append(str(proc.info["pid"]))
        except Exception:
            pass

        if vpn_slice_pids:
            evidence.append(f"[Process] 'vpn-slice' is running (PIDs: {', '.join(vpn_slice_pids)})")
        else:
            evidence.append("[Process] 'vpn-slice' is NOT running")

        if openconnect_pids:
            evidence.append(f"[Process] 'openconnect' is running (PIDs: {', '.join(openconnect_pids)})")
        else:
            evidence.append("[Process] 'openconnect' is NOT running")

        return evidence

    def disconnect(self) -> None:
        console.info("Disconnecting OpenConnect...")
        if self._pid:
            try:
                os.kill(self._pid, 2) # SIGINT
                time.sleep(2)
                if psutil.pid_exists(self._pid):
                    os.kill(self._pid, 15) # SIGTERM
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
            pass

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
        self.disconnect()
        commands = self.get_reset_commands(service)
        if not commands:
            return True
        success = True
        for cmd in commands:
            target = cmd.split()[-1]
            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if res.returncode != 0 and "not found" not in res.stderr.lower():
                    host_cmd = f"sudo route delete {target}"
                    res_host = subprocess.run(host_cmd, shell=True, capture_output=True, text=True)
                    if res_host.returncode != 0 and "not found" not in res_host.stderr.lower():
                        success = False
            except Exception:
                success = False
        return success