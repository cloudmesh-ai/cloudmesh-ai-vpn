from typing import Optional, Type

from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.vpn.strategies.linux import LinuxVpnStrategy


def get_linux_strategy_class(provider: Optional[str] = None) -> Type[VpnOSStrategy]:
    """Return the Linux VPN strategy class."""
    return LinuxVpnStrategy
