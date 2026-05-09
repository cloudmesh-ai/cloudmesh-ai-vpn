import os
import subprocess
import time
import sys
import psutil
from cloudmesh.ai.vpn.vpn import VpnDependencyError
import re
from typing import Any, Dict, List, Union, Optional

from cloudmesh.ai.common.io import console
from cloudmesh.ai.common.logging_utils import get_contextual_logger
from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.vpn.organizations import organizations

logger = get_contextual_logger("vpn.linux")

def path_expand(path):
    return os.path.expanduser(path)

class LinuxVpnStrategy(VpnOSStrategy):
    def __init__(self, vpn_context: 'Vpn'):
        super().__init__(vpn_context)
        self._pid = None

    def _discover_openconnect(self) -> Optional[str]:
        return self._discover_binary("openconnect", ["/usr/bin/openconnect", "/usr/local/bin/openconnect"])

    def _discover_anyconnect(self) -> Optional[str]:
        return self._discover_binary("vpnui", ["/opt/cisco/anyconnect/bin/vpnui", "/usr/bin/vpnui"])

    def _discover_vpn_slice(self) -> Optional[str]:
        return self._discover_binary("vpn-slice", ["/usr/local/bin/vpn-slice", "/usr/bin/vpn-slice"])

    @property
    def vpn_slice(self) -> Optional[str]:
        return self._discover_vpn_slice()

    def is_enabled(self) -> bool:
        for proc in psutil.process_iter(attrs=["name"]):
            if proc.info["name"] == "openconnect": return True
        return False

    def connect(self, creds: Dict[str, Any], vpn_name: str, no_split: bool, progress_callback: Optional[callable] = None) -> Union[bool, str, None]:
        if progress_callback:
            progress_callback(f"Starting connection process for {vpn_name}...")
        oc_exe = self.openconnect
        if not oc_exe:
            console.error("OpenConnect binary not found. Please install it via your package manager.")
            return False
        
        host = organizations[vpn_name]["host"]
        

        if progress_callback:
            progress_callback("Preparing routing and connection parameters...")
        # Handle Routing Script - vpn-slice is assumed to be installed
        script_arg = ""
        if not no_split:
            vs_exe = self.vpn_slice or "vpn-slice"
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
        
        # Add -b for background and -v for verbose as per README-tech
        cmd_list = ["sudo", oc_exe, "-b", "-v", "--protocol=anyconnect", "-u", user]
        
        # Docker MTU Fix
        is_docker = os.path.exists("/.dockerenv") or (os.path.isfile("/proc/self/cgroup") and "docker" in open("/proc/self/cgroup").read())
        if is_docker:
            cmd_list.extend(["-m", "1290"])

        if auth_method == "cert":
            # Linux often uses a 3-file cert set: cafile, sslkey, certificate
            cert_path = org_config.get("cert") or creds.get("cert_path")
            if not cert_path:
                cert_path = "~/.ssh/uva/"
            
            # Ensure cert_path is a string (handle cases where it might be a list)
            if isinstance(cert_path, list):
                cert_path = cert_path[0] if cert_path else "~/.ssh/uva/"
            
            expanded_path = path_expand(str(cert_path))
            
            if os.path.isdir(expanded_path):
                # Use the 3-file set documented in README-tech
                cmd_list.extend([
                    "--cafile", os.path.join(expanded_path, "usher.cer"),
                    "--sslkey", os.path.join(expanded_path, "user.key"),
                    "--certificate", os.path.join(expanded_path, "user.crt")
                ])
            elif os.path.exists(expanded_path):
                # Fallback to single decrypted PEM
                cmd_list.extend(["-c", expanded_path])
            else:
                console.error(f"Certificate file or directory not found at {cert_path}")
                return False
        else:
            # Password auth
            pw = creds.get("pw")
            if pw:
                cmd_list.append("--passwd-on-stdin")

        if script_arg:
            cmd_list.extend(["--script", script_arg])
        
        cmd_list.append(host)
        
        # Log the exact command for debugging
        cmd_str = ' '.join(cmd_list)
        logger.debug(f"[VPN] Executing command: {cmd_str}")
        
        if progress_callback:
            progress_callback("Launching OpenConnect process...")
        try:
            # Use DEVNULL for stdout/stderr because -b (background) mode 
            # will hang if the pipe buffers fill up and we aren't reading them.
            proc = subprocess.Popen(
                cmd_list,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1 # Line buffered
            )
            
            # Move the process to its own process group for persistence (as per README-tech)
            try:
                os.setpgid(proc.pid, 0)
            except (ProcessLookupError, PermissionError):
                pass

            if auth_method != "cert":
                pw = creds.get("pw")
                if pw:
                    console.info("Sending password to stdin...")
                    try:
                        # Some versions of openconnect/sudo need a small delay before password
                        time.sleep(1)
                        proc.stdin.write(pw + "\n")
                        proc.stdin.flush()
                        console.info("Password sent successfully.")
                    except Exception as e:
                        console.error(f"Failed to write password to stdin: {e}")
                        logger.debug(f"Failed to write password to stdin: {e}")

            # Give it a moment to start and potentially fail
            console.info("Waiting 5 seconds for process to initialize...")
            time.sleep(5)
            
            # Check if the process died immediately with an error
            if proc.poll() is not None and proc.returncode != 0:
                console.error(f"OpenConnect failed to start immediately with exit code {proc.returncode}.")
                return False

            console.info("Verifying connection process...")
            # Verify if OpenConnect is running. Since -b detaches the process,
            # we check for any running openconnect process.
            try:
                for p in psutil.process_iter(["pid", "name"]):
                    if p.info["name"] and "openconnect" in p.info["name"].lower():
                        self._pid = p.info["pid"]
                        console.info(f"Successfully tracked OpenConnect PID: {self._pid}")
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            # Fallback: check if the sudo process is still running
            if proc.poll() is None:
                self._pid = proc.pid
                console.info(f"Tracking sudo PID: {self._pid}")
                return True
                
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
            # Extract routes from vpn-slice command line
            try:
                out = subprocess.check_output(["ps", "aux"], text=True)
                for line in out.splitlines():
                    if "vpn-slice" in line:
                        routes = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?", line)
                        if routes:
                            # Filter out the binary path if it contains an IP-like string
                            filtered_routes = [r for r in routes if r not in line.split("/bin/")[0]]
                            evidence.append(f"[OpenConnect] Routes configured via vpn-slice: {', '.join(filtered_routes)}")
                        else:
                            evidence.append("[OpenConnect] Running with vpn-slice but no routes detected in command line")
                        break
            except Exception:
                pass
        else:
            evidence.append("[Process] 'openconnect' is NOT running")

        # Routing table check
        try:
            current_org = self.get_current_org()
            org_name = current_org.lower() if current_org else self.vpn.service_key.lower()
            ip_range = organizations.get(org_name, {}).get("ip")
            
            if ip_range:
                targets = ip_range if isinstance(ip_range, list) else [ip_range]
                route_out = subprocess.check_output(["netstat", "-rn"], text=True)
                for target in targets:
                    search_ip = target.split("/")[0].strip()
                    if re.search(rf"^\s*{re.escape(search_ip)}(\s+|/)", route_out, re.MULTILINE):
                        display_net = target if "/" in target else f"{target}/16"
                        evidence.append(f"[Routing Table] Route to {display_net} found in system routing table (netstat -rn) (Org: {org_name})")
        except Exception:
            pass
 
        return evidence

    def check_dependencies(self, choco: bool = False) -> None:
        """Check if required binaries are installed."""
        try:
            subprocess.run(["openconnect", "-V"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["vpn-slice", "-h"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise VpnDependencyError(
                "Required binaries (openconnect or vpn-slice) not found. "
                "Please install them using your package manager (e.g., sudo apt install openconnect)."
            )

    def disconnect(self) -> None:
        console.info("Disconnecting OpenConnect...")
        from cloudmesh.ai.common.Shell import Shell
        
        # 1. Try graceful shutdown
        try:
            Shell.run("sudo pkill -SIGINT openconnect")
        except Exception:
            pass
        try:
            Shell.run("sudo pkill -SIGINT vpn-slice")
        except Exception:
            pass
        time.sleep(2)
        
        # 2. Force kill any remaining processes to prevent PID accumulation
        try:
            Shell.run("sudo pkill -9 openconnect")
        except Exception:
            pass
        try:
            Shell.run("sudo pkill -9 vpn-slice")
        except Exception:
            pass
        
        logger.debug("[VPN] Forced disconnect of all openconnect and vpn-slice processes.")

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