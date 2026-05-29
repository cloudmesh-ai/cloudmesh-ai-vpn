import os
import subprocess
import time
import sys
import psutil
import pty
from typing import Any, Dict, List, Union, Optional

from cloudmesh.ai.common.io import console
import os

def path_expand(path):
    return os.path.expanduser(path)
from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.vpn.organizations import organizations

class MacOpenConnectDecryptedStrategy(VpnOSStrategy):
    def __init__(self, vpn_context: 'Vpn'):
        super().__init__(vpn_context)
        self._pid = None

    def _discover_openconnect(self) -> Optional[str]:
        return self._discover_binary("openconnect", ["/usr/bin/openconnect", "/usr/local/bin/openconnect", "/opt/homebrew/bin/openconnect"])

    def _discover_anyconnect(self) -> Optional[str]:
        return None

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

    def connect(self, creds: Dict[str, Any], vpn_name: str, no_split: bool, progress_callback: Optional[callable] = None) -> Union[bool, str, None]:
        if progress_callback:
            progress_callback("Checking dependencies...")
        oc_exe = self.openconnect
        if not oc_exe:
            console.error("OpenConnect binary not found. Please install it via Homebrew: brew install openconnect")
            return False
        
        vs_exe = self.vpn_slice
        if not vs_exe and not no_split:
            console.error("vpn-slice binary not found. Please install it: brew install vpn-slice")
            return False

        host = organizations[vpn_name]["host"]
        

        script_arg = ""
        if not no_split:
            org_config = organizations.get(vpn_name, {})
            ip_range = org_config.get("ip")
            if isinstance(ip_range, list):
                slice_target = " ".join(ip_range)
            else:
                slice_target = ip_range if ip_range else host
            script_arg = f"--script='{vs_exe} -v {slice_target}'"

        user_val = creds.get('user')
        if not isinstance(user_val, str):
            org_config = organizations.get(vpn_name, {})
            user_val = org_config.get('username') or org_config.get('user')
        
        if not isinstance(user_val, str):
            import getpass
            user = getpass.getuser()
        else:
            user = user_val

        cert_path = creds.get("cert_path")
        if not cert_path:
            default_cert = os.path.expanduser("~/.ssh/uva/decrypted_user.pem")
            if os.path.exists(default_cert):
                cert_path = default_cert
            else:
                console.error("cert_path is required for openconnect-decrypted provider (default ~/.ssh/uva/decrypted_user.pem not found)")
                return False
        
        # Use standard sudo since password is now cached via sudo -v
        command = f"sudo {oc_exe} --protocol=anyconnect -u {user} -c {path_expand(cert_path)} {script_arg} {host}"
        if self.vpn.verbosity >= 1:
            console.info(f"Connecting via OpenConnect (Decrypted): {command}")
        
        # To make the VPN persist in the background, we use subprocess.Popen with start_new_session=True.
        # Since we might need to provide a password, we use --passwd-on-stdin.
        
        final_command = command
        pw = creds.get("pw")
        if pw:
            final_command = f"{command} --passwd-on-stdin"
        
        if progress_callback:
            progress_callback("Launching OpenConnect (Decrypted)...")
        try:
            # Construct the command as a list to avoid shell=True and TTY issues with sudo.
            cmd_list = ["sudo", oc_exe, "--protocol=anyconnect"]
            if self.vpn.verbosity == 0:
                cmd_list.append("-q")
            cmd_list.extend(["-u", user, "-c", path_expand(cert_path)])
            if script_arg:
                # script_arg is like "--script='...'"
                # We need to split it into two elements: "--script" and the actual script
                # Since script_arg was constructed as f"--script='{vs_exe} -v {slice_target}'"
                # we'll just manually add the parts.
                vs_exe_path = self.vpn_slice
                org_config = organizations.get(vpn_name, {})
                ip_range = org_config.get("ip")
                if isinstance(ip_range, list):
                    slice_target = " ".join(ip_range)
                else:
                    slice_target = ip_range if ip_range else host
                
                slice_v = "-v " if self.vpn.verbosity >= 1 else ""
                cmd_list.extend(["--script", f"{vs_exe_path} {slice_v}{slice_target}"])
            
            cmd_list.append(host)
            
            if pw:
                cmd_list.append("--passwd-on-stdin")
            
            # Use subprocess.Popen without start_new_session=True to maintain TTY association for sudo.
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
                text=True
            )

            if verbosity >= 2:
                import threading
                def stream_output(pipe, prefix):
                    for line in iter(pipe.readline, ""):
                        console.print(f"{prefix} {line.strip()}")
                
                threading.Thread(target=stream_output, args=(proc.stdout, "[OpenConnect-Out]"), daemon=True).start()
                threading.Thread(target=stream_output, args=(proc.stderr, "[OpenConnect-Err]"), daemon=True).start()
            
            # Move the process to its own process group so it doesn't receive SIGHUP when the parent exits.
            try:
                os.setpgid(proc.pid, 0)
            except (ProcessLookupError, PermissionError):
                pass # Ignore if we can't set pgid (e.g. due to sudo privilege change)
            
            if pw:
                proc.stdin.write(pw + "\n")
                proc.stdin.flush()
            
            # Wait a bit to ensure the process has started.
            time.sleep(2)
            
            # Find the PID of the actual openconnect process.
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
        if self.vpn.verbosity >= 1:
            console.info("Disconnecting OpenConnect...")
        if self._pid:
            try:
                if self.vpn.verbosity >= 1:
                    console.info(f"Sending SIGINT to OpenConnect process {self._pid}")
                os.kill(self._pid, 2)  # SIGINT
                time.sleep(2)
                if psutil.pid_exists(self._pid):
                    console.warning(f"Process {self._pid} still exists, forcing termination")
                    os.kill(self._pid, 15) # SIGTERM
            except ProcessLookupError:
                pass
            except Exception as e:
                console.error(f"Error during targeted disconnect: {e}")
        else:
            from cloudmesh.ai.common.Shell import Shell
            redirect = " &> /dev/null" if self.vpn.verbosity == 0 else ""
            Shell.run(f"sudo pkill -SIGINT openconnect{redirect}")
        
        from cloudmesh.ai.common.Shell import Shell
        try:
            redirect = " &> /dev/null" if self.vpn.verbosity == 0 else ""
            Shell.run(f"sudo pkill vpn-slice{redirect}")
        except Exception:
            pass # Ignore if vpn-slice is already gone

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
                    res_host = subprocess.run(host_cmd, shell=True, capture_output=True, text=True)
                    if res_host.returncode != 0 and "not found" not in res_host.stderr.lower():
                        console.error(f"Failed to remove route {target}: {res_host.stderr.strip()}")
                        success = False
            except Exception as e:
                console.error(f"Exception while removing route {target}: {e}")
                success = False
        return success
