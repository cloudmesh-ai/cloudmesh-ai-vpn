from typing import Optional, Type

from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.vpn.strategies.windows import WindowsVpnStrategy


def get_windows_strategy_class(provider: Optional[str] = None) -> Type[VpnOSStrategy]:
    """Return the Windows VPN strategy class."""
    return WindowsVpnStrategy
