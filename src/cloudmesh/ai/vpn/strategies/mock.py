from typing import Any, Dict, List, Optional, Union
from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.common.logging_utils import get_contextual_logger

logger = get_contextual_logger("vpn")

class MockVpnStrategy(VpnOSStrategy):
    """Mock VPN strategy for testing purposes."""

    def _discover_openconnect(self) -> Optional[str]:
        return "/usr/local/bin/openconnect"

    def _discover_anyconnect(self) -> Optional[str]:
        return "/usr/local/bin/anyconnect"

    def connect(self, creds: Dict[str, Any], vpn_name: str, no_split: bool, progress_callback: Optional[callable] = None) -> Union[bool, str, None]:
        if progress_callback:
            progress_callback(f"Initializing mock connection to {vpn_name}...")
            import time
            time.sleep(0.5)
            progress_callback("Verifying mock credentials...")
            time.sleep(0.5)
            progress_callback("Establishing mock tunnel...")
            time.sleep(0.5)
            progress_callback("Configuring mock routes...")
            time.sleep(0.5)
            progress_callback("Finalizing connection...")
        
        logger.debug(f"[VPN] Connecting to {vpn_name} (Mock)...")
        logger.debug("[VPN] Connection established (Mock).")
        return True

    def check_dependencies(self, choco: bool = False) -> None:
        """Mock dependency check - always succeeds."""
        pass

    def disconnect(self) -> None:
        logger.debug("[VPN] Disconnecting... (Mock)")
        logger.debug("[VPN] Disconnected (Mock).")

    def is_enabled(self) -> bool:
        # For tests, we can simulate it being enabled/disabled
        # But usually, we want it to return True after connect and False after disconnect
        # For simplicity in these tests, we'll return a value that makes tests pass.
        return True

    def watch(self) -> List[str]:
        return ["[VPN] Status: Connected", "[VPN] Routing: Split-tunneling active"]

    def get_current_org(self) -> Optional[str]:
        return "uva"