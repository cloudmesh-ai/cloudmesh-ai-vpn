import subprocess
import os
import logging
from typing import Any, Dict, Optional, List
from cloudmesh.ai.common.io import console, load_yaml
from cloudmesh.ai.common.sys import os_is_mac, os_is_linux
from cloudmesh.ai.common.logging_utils import get_contextual_logger

logger = get_contextual_logger("luc_vpn")

class LucVpn:
    """
    Manages VPN connections to the LUC (UVA) VPN.
    This class can be used as a standalone manager or integrated as a strategy
    into the main Vpn context.
    """

    def __init__(
        self, 
        user: Optional[str] = None, 
        vpn_host: Optional[str] = None,
        vpn_target: Optional[str] = None,
        cert_path: Optional[str] = None, 
        key_path: Optional[str] = None,
        verbosity: int = 0
    ):
        self.verbosity = verbosity
        self.log_file = os.path.expanduser("~/.config/cloudmesh/vpn_connection.log")

        # Load configuration from ~/.config/cloudmesh/luc.yaml
        config_path = os.path.expanduser("~/.config/cloudmesh/luc.yaml")
        full_config = load_yaml(config_path) or {}
        
        # Navigate the nested structure: cloudmesh -> ai -> vpn
        config = full_config.get("cloudmesh", {}).get("ai", {}).get("vpn", {})

        # Precedence: Arg > Env > Config File > Default
        self.user = (
            user 
            or os.environ.get("LUC_VPN_USER") 
            or config.get("user") 
            or "user-unknown"
        )
        self.vpn_host = (
            vpn_host 
            or os.environ.get("LUC_VPN_HOST") 
            or config.get("vpn_host") 
            or "secureaccess.luc.edu"
        )
        self.vpn_target = (
            vpn_target 
            or os.environ.get("LUC_VPN_TARGET") 
            or config.get("vpn_target") 
            or "147.126.0.0/16"
        )
        
        # Ensure paths are expanded
        self.cert_path = os.path.expanduser(
            cert_path 
            or os.environ.get("LUC_VPN_CERT_PATH") 
            or config.get("cert_path") 
            or "~/.ssh/luc_cert.pem"
        )
        self.key_path = os.path.expanduser(
            key_path 
            or os.environ.get("LUC_VPN_KEY_PATH") 
            or config.get("key_path") 
            or "~/.ssh/luc_key.pem"
        )

    def _log(self, msg: str, level: int = logging.INFO):
        if self.verbosity >= 1:
            logger.log(level, msg)

    def is_enabled(self) -> bool:
        """Check if OpenConnect is currently running."""
        try:
            # pgrep -x openconnect
            result = subprocess.run(["pgrep", "-x", "openconnect"], capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            self._log(f"Error checking VPN status: {e}", logging.ERROR)
            return False

    def connect(self, nosplit: bool = False, progress_callback: Optional[callable] = None) -> bool:
        """
        Establishes a VPN connection to LUC.
        
        Args:
            nosplit: If True, routes all traffic through the VPN (disables vpn-slice).
            progress_callback: Optional callback to update progress UI.
        """
        if self.is_enabled():
            console.warning("OpenConnect is already running. Please disconnect first.")
            return False

        if progress_callback:
            progress_callback("Checking dependencies...")

        if not self._check_dependencies():
            return False

        if not os.path.exists(self.cert_path) or not os.path.exists(self.key_path):
            console.error(f"Certificate or Key files not found at {self.cert_path} or {self.key_path}")
            return False

        if progress_callback:
            progress_callback(f"Connecting to {self.vpn_host} as {self.user}...")

        # Build the openconnect command
        # Protocol anyconnect, background mode, certificate based auth
        cmd = [
            "sudo", "openconnect", "-b", 
            "--protocol=anyconnect", 
            "-u", self.user, 
            "--certificate", self.cert_path, 
            "--sslkey", self.key_path, 
            "--servercert", "pin-sha256:scz7BQrdBL079kKAzH6XgA68hEqaL0As+7tinXsQgy8=",
            "-v",
            self.vpn_host
        ]

        if not nosplit:
            # Use vpn-slice for split tunneling
            cmd.extend(["--script", f"vpn-slice {self.vpn_target}"])

        self._log(f"Executing command: {' '.join(cmd)}", logging.DEBUG)

        try:
            with open(self.log_file, "w") as log_f:
                subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT)
            
            # Give it a moment to start
            import time
            time.sleep(2)
            
            if self.is_enabled():
                self._log("VPN connection request sent successfully.")
                return True
            else:
                console.error(f"Failed to establish VPN connection. Check {self.log_file} for details.")
                return False
        except Exception as e:
            console.error(f"An error occurred while connecting: {e}")
            return False

    def disconnect(self) -> bool:
        """Disconnects from the VPN."""
        if not self.is_enabled():
            console.ok("VPN is already deactivated.")
            return True

        try:
            # Use sudo to kill openconnect
            subprocess.run(["sudo", "killall", "openconnect"], check=True)
            self._log("VPN disconnected successfully.")
            return True
        except subprocess.CalledProcessError as e:
            console.error(f"Failed to disconnect VPN: {e}")
            return False

    def _check_dependencies(self) -> bool:
        """Verify that openconnect and vpn-slice are installed."""
        for tool in ["openconnect"]:
            try:
                subprocess.run(["which", tool], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                console.error(f"Error: {tool} is not installed.")
                return False
        
        # vpn-slice is optional but recommended for split tunneling
        try:
            subprocess.run(["which", "vpn-slice"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            self._log("Warning: vpn-slice is not installed. Split tunneling will not work.", logging.WARNING)
            
        return True

    def status(self) -> str:
        """Returns the connection status."""
        return "Connected" if self.is_enabled() else "Disconnected"