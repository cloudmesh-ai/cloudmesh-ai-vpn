import os
import subprocess
import time
import sys
import json
from typing import Any, Dict, Optional, Union, List

import requests
import keyring as kr

from cloudmesh.ai.common.io import console, load_yaml
from cloudmesh.ai.common.logging_utils import get_contextual_logger
from rich.table import Table
from rich.box import ROUNDED
from cloudmesh.ai.common.sys import os_is_linux, os_is_mac, os_is_windows

logger = get_contextual_logger("vpn")


class VpnDependencyError(Exception):
    """Exception raised when a required VPN dependency is missing."""
    pass

from cloudmesh.ai.vpn.organizations import organizations as org_config

from cloudmesh.ai.vpn.factory import get_vpn_strategy_class
from cloudmesh.ai.vpn.key_manager import KeyManager
from cloudmesh.ai.vpn.config import VpnConfig




class Vpn:
    """Context class for managing VPN connections using OS-specific strategies."""

    def __init__(
        self,
        service: Optional[str] = None,
        timeout: Optional[int] = None,
        debug: bool = False,
        provider: Optional[str] = None,
        profile_name: Optional[str] = None,
    ) -> None:
        self.timeout = timeout or 60
        self.debug = debug
        self.profile_name = profile_name

        # Use VpnConfig for flexible configuration loading and merging
        self.vpn_config = VpnConfig(service=service, profile_name=profile_name)
        self.service_key = self.vpn_config.service.lower()
        self.service = self.vpn_config.service
        self.config = self.vpn_config.config

        # Strategy Selection
        strategy_class = get_vpn_strategy_class(provider)
        self.strategy = strategy_class(self)

        if os_is_mac():
            console.msg(f"Selected VPN Strategy: {self.strategy.__class__.__name__}")

    def _debug(self, msg: str) -> None:
        if self.debug:
            logger.debug(msg)

    def is_user_auth(self, org: str) -> bool:
        # Use a temporary config for the requested org to check auth
        temp_config = VpnConfig(service=org)
        return temp_config.get("user", False)

    def enabled(self) -> bool:
        return self.strategy.is_enabled()

    def warmup_sudo(self) -> bool:
        """Warm up sudo to cache the system password before starting progress UI."""
        from cloudmesh.ai.common.sudo import Sudo
        return Sudo.password() == 0

    def connect(self, creds: Optional[Dict[str, Any]] = None, progress_callback: Optional[callable] = None) -> Union[bool, str, None]:
        if creds is None:
            creds = {}
        
        no_split = creds.get("nosplit", True)
        vpn_name = creds.get("service", "uva")

        # Capture state before action
        before_org = self.strategy.get_current_org()

        result = self.strategy.connect(creds, vpn_name, no_split, progress_callback=progress_callback)

        if result:
            # Capture state after action
            after_org = self.strategy.get_current_org()
            if before_org and after_org and before_org != after_org:
                console.ok(f"Switched from {before_org} to {after_org}")
            elif after_org:
                console.ok(f"Connected to {after_org}")
            else:
                console.warning(
                    "Connection command succeeded, but could not verify organization via IP."
                )

        return result

    def disconnect(self) -> None:
        # Capture state before action
        before_org = self.strategy.get_current_org()

        if not self.enabled():
            console.ok("VPN is already deactivated")
            return

        self.strategy.disconnect()

        if self.enabled():
            console.error("VPN is still enabled. Disconnection may have failed.")
        else:
            if before_org:
                console.ok(f"Disconnected from {before_org}")
            else:
                console.ok("Successfully disconnected from VPN.")

    def get_reset_commands(self, service: Optional[str] = None) -> List[str]:
        return self.strategy.get_reset_commands(service)

    def reset_routes(self, service: Optional[str] = None) -> bool:
        return self.strategy.reset_routes(service)


    def info(self) -> str:
        """Display current IP information in a rich table using multiple fallback providers."""
        if os.environ.get("VPN_MOCK") == "1":
            logger.debug("[VPN Info] Location: UVA Campus")
            logger.debug("[VPN Info] IP: 128.118.x.x")
            return '{"location": "UVA Campus", "ip": "128.118.x.x"}'

        providers = [
            {"url": "https://ipinfo.io/json", "type": "json"},
            {"url": "https://ifconfig.me/all.json", "type": "json"},
            {"url": "https://api.ipify.org?format=json", "type": "json"},
            {"url": "https://icanhazip.com", "type": "text"},
        ]

        data = {}
        for provider in providers:
            try:
                res = requests.get(provider["url"], timeout=5)
                if res.status_code == 429:
                    console.warning(
                        f"Provider {provider['url']} rate limited (429). Trying next..."
                    )
                    continue
                res.raise_for_status()

                if provider["type"] == "json":
                    data = res.json()
                else:
                    data = {"ip": res.text.strip()}

                # If we got a valid IP, we can stop
                if data.get("ip") or data.get("query"):
                    break
            except Exception as e:
                console.error(
                    f"Provider {provider['url']} failed: {type(e).__name__}: {e}"
                )
                continue

        if not data:
            console.error(
                "All IP information providers failed to return a valid IP address."
            )
            return ""

        try:
            table = Table(
                title="IP Information",
                box=ROUNDED,
                show_header=True,
                header_style="bold magenta",
            )
            table.add_column("Field", style="cyan", width=15)
            table.add_column("Value", style="cyan")

            for key, value in data.items():
                table.add_row(key, str(value))

            console.print(table)
            return json.dumps(data, indent=2)
        except Exception as e:
            console.error(f"Failed to render IP info table: {e}")
            return ""

    def pw_fetcher(self, org: str):
        if os.environ.get("VPN_MOCK") == "1":
            return "mock-user", "mock-password"

        # Use a temporary config for the requested org to check auth
        temp_config = VpnConfig(service=org)
        if not temp_config.config:
            console.error(f"Unknown service {org}")
            return False

        if temp_config.get("auth") == "pw":
            # 1. Determine username: Profile override -> Keyring -> Prompt
            username = self.config.get("user")
            if not username:
                username = kr.get_password(org, "cloudmesh-user")

            if username and username.upper() == "TBD":
                console.error(
                    f"Username for {org} is set to 'TBD'. Please update your profile or keyring."
                )
                os._exit(1)

            stored_pw = kr.get_password(org, "cloudmesh-pw")

            if stored_pw is None:
                import getpass

                if not username:
                    username = input(f"Enter your {org} username: ")

                console.msg(f"Using username: {username}")
                while True:
                    password = getpass.getpass(f"Enter your {org} password: ")
                    confirm_password = getpass.getpass("Confirm your password: ")
                    if password == confirm_password:
                        break
                    console.error("Passwords do not match. Please try again.")

                kr.set_password(org, "cloudmesh-pw", password)
                kr.set_password(org, "cloudmesh-user", username)
                stored_pw = password

            return username, stored_pw
        return False

    def pw_clearer(self, org: str):
        if os.environ.get("VPN_MOCK") == "1":
            console.ok(f"Credentials for {org} have been cleared (Mock).")
            return True

        # Use a temporary config for the requested org to verify it exists
        temp_config = VpnConfig(service=org)
        if not temp_config.config:
            console.error(f"Unknown service {org}")
            return False
        kr.delete_password(org, "cloudmesh-pw")
        kr.delete_password(org, "cloudmesh-user")
        console.ok(f"Credentials for {org} have been cleared.")

    def watch(self) -> List[str]:
        """Check for evidence that the VPN is active and using split-routing."""
        return self.strategy.watch()

    def validate_keys(self, cert_path: str, key_path: str, ca_path: Optional[str]) -> Dict[str, Any]:
        """Verify VPN certificates and keys using the KeyManager."""
        return KeyManager.validate_keys(cert_path, key_path, ca_path)

    def init_keys(self, p12_path: str, output_dir: str) -> bool:
        """Initialize VPN keys from a .p12 bundle using the KeyManager."""
        return KeyManager.init_keys(p12_path, output_dir)
