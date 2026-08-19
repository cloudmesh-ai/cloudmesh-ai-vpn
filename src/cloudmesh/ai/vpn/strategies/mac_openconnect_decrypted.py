import os
import subprocess
import time
import sys
import psutil
import pty
import fcntl
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
        
        # Pre-flight check: Sudo privileges
        # We rely on vpn.warmup_sudo() called in the command layer to cache credentials.
        # No further interactive checks are performed here to avoid blocking the background process.

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
        # Include server certificate in the log string for visibility
        org_config = organizations.get(vpn_name, {})
        server_cert = org_config.get("server_cert")
        cert_flag = f" --servercert {server_cert}" if server_cert else ""
        
        command = f"sudo {oc_exe} --protocol=anyconnect -u {user} -c {path_expand(cert_path)}{cert_flag} {script_arg} {host}"
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
            
            # We avoid adding '-q' (quiet mode) because it can suppress the success markers 
            # we need to monitor in the log file to detect a successful connection.
            
            # Handle server certificate pinning from organization config
            org_config = organizations.get(vpn_name, {})
            server_cert = org_config.get("server_cert")
            if server_cert:
                cmd_list.extend(["--servercert", server_cert])
                
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
            
            # To prevent SIGPIPE crashes when the parent exits, we redirect output to a log file
            # instead of using pipes. We then tail this file to monitor for success.
            org_config = organizations.get(vpn_name, {})
            log_path = org_config.get("log_file", "~/.config/cloudmesh/vpn_openconnect.log")
            log_file_path = os.path.expanduser(log_path)
            log_file = open(log_file_path, "w+")
            
            proc = subprocess.Popen(
                cmd_list,
                stdin=subprocess.PIPE,
                stdout=log_file,
                stderr=subprocess.STDOUT, # Merge stderr into stdout for easier tailing
                text=True,
                bufsize=1
            )

            # Move the process to its own process group
            try:
                os.setpgid(proc.pid, 0)
            except (ProcessLookupError, PermissionError):
                pass

            if pw:
                proc.stdin.write(pw + "\n")
                proc.stdin.flush()

            # Monitoring loop for success or failure
            # Increased timeout to 60s because some servers (like UVA) can be erratic 
            # with initial handshakes (404s/302s) before succeeding.
            timeout = 60
            start_time = time.time()
            success_markers = [
                "Established DTLS connection", 
                "Connected as", 
                "CSTP connected", 
                "VPN connection established",
                "HTTP/1.1 200 OK"
            ]
            
            last_pos = 0
            while time.time() - start_time < timeout:
                # Check if process exited
                exit_code = proc.poll()
                if exit_code is not None:
                    log_file.seek(0)
                    error_logs = log_file.read()
                    console.error(f"OpenConnect exited prematurely with code {exit_code}")
                    if error_logs:
                        console.error(f"Logs: {error_logs.strip()}")
                    log_file.close()
                    return False

                # Tail the log file
                log_file.seek(last_pos)
                lines = log_file.readlines()
                last_pos = log_file.tell()
                
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    
                    if self.vpn.verbosity >= 1:
                        console.print(f"[OpenConnect] {line}")
                    
                    if any(marker in line for marker in success_markers):
                        self._pid = proc.pid
                        log_file.close()
                        return True
                    
                
                time.sleep(0.1)

            console.error(f"VPN connection timed out after {timeout} seconds.")
            
            # Debugging: Print the last few lines of the log to diagnose the timeout
            log_file.seek(0)
            full_log = log_file.read()
            if full_log:
                lines = full_log.splitlines()
                last_lines = lines[-10:]
                console.print("\n[bold red]Last 10 lines of VPN log:[/bold red]")
                for line in last_lines:
                    console.print(f"  {line}")
            else:
                console.error("VPN log is empty. OpenConnect may have failed to start.")
                
            log_file.close()
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
            try:
                import re
                out = subprocess.check_output(["ps", "aux"], text=True)
                for line in out.splitlines():
                    if "vpn-slice" in line:
                        routes = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?", line)
                        if routes:
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
        org_config = organizations.get(org_name, {})
        ip_range = org_config.get("ip")
        
        if ip_range:
            targets = ip_range if isinstance(ip_range, list) else [ip_range]
            try:
                import re
                route_out = subprocess.check_output(["netstat", "-rn"], text=True)
                routes_found = 0
                for target in targets:
                    search_ip = target.split("/")[0].strip()
                    if re.search(rf"^\s*{re.escape(search_ip)}(\s+|/)", route_out, re.MULTILINE):
                        routes_found += 1
                
                if routes_found > 0:
                    evidence.append(f"[Routing Table] {routes_found}/{len(targets)} routes verified in system routing table (Org: {org_name})")
                else:
                    evidence.append(f"[Routing Table] No routes found for {org_name}")
            except Exception:
                pass

        # 5. DNS Verification
        test_host = org_config.get("dns_test_host") or org_config.get("dns")
        if test_host:
            try:
                import socket
                socket.gethostbyname(test_host)
                evidence.append(f"[DNS] Successfully resolved {test_host} (VPN DNS is working)")
            except socket.gaierror:
                evidence.append(f"[DNS] Failed to resolve {test_host} (VPN DNS might be broken)")
            except Exception as e:
                evidence.append(f"[DNS] DNS check failed: {e}")

        return evidence

    def _get_active_network_service(self) -> Optional[str]:
        """Maps the active interface to a networksetup service name."""
        try:
            # Get active interface from default route
            route_out = subprocess.check_output(["route", "get", "default"], text=True)
            for line in route_out.splitlines():
                if line.startswith("interface:"):
                    iface = line.split(":")[1].strip()
                    break
            else:
                return None

            # Map interface to service name using networksetup
            services_out = subprocess.check_output(["networksetup", "-listnetworkserviceorder"], text=True)
            current_service = None
            for line in services_out.splitlines():
                if current_service is None and line.startswith("("):
                    current_service = line.strip("() ")
                elif current_service and f"Device: {iface}" in line:
                    return current_service
                elif line.startswith("("):
                    current_service = line.strip("() ")
            return None
        except Exception:
            return None

    def disconnect(self) -> None:
        if self.vpn.verbosity >= 1:
            console.info("Disconnecting OpenConnect...")
        
        if self._pid:
            try:
                if self.vpn.verbosity >= 1:
                    console.info(f"Killing process group for PID {self._pid}")
                # Kill the entire process group (PGID is the same as PID of the group leader)
                os.killpg(os.getpgid(self._pid), 15) # SIGTERM
            except (ProcessLookupError, PermissionError) as e:
                if self.vpn.verbosity >= 1:
                    console.warning(f"Could not kill process group: {e}")
                # Fallback to individual PID
                try:
                    os.kill(self._pid, 15)
                except:
                    pass
            except Exception as e:
                console.error(f"Error during targeted disconnect: {e}")
        else:
            from cloudmesh.ai.common.Shell import Shell
            redirect = " &> /dev/null" if self.vpn.verbosity == 0 else ""
            Shell.run(f"sudo pkill -SIGTERM openconnect{redirect}")
        
        from cloudmesh.ai.common.Shell import Shell
        try:
            redirect = " &> /dev/null" if self.vpn.verbosity == 0 else ""
            Shell.run(f"sudo pkill -SIGTERM vpn-slice{redirect}")
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
