import os
from importlib import import_module
from typing import Optional, Type
from cloudmesh.ai.common.sys import os_is_linux, os_is_mac, os_is_windows
from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.vpn.strategies.mock import MockVpnStrategy


def _load_factory(module_name: str, function_name: str):
    module = import_module(module_name)
    return getattr(module, function_name)

def get_vpn_strategy_class(provider: Optional[str] = None) -> Type[VpnOSStrategy]:
    """
    Factory function to return the appropriate VPN strategy class based on OS and provider.
    """
    if os.environ.get("VPN_MOCK") == "1":
        return MockVpnStrategy
    
    if os_is_windows():
        return _load_factory(
            "cloudmesh.ai.vpn.windows_factory", "get_windows_strategy_class"
        )(provider)
    
    if os_is_linux():
        return _load_factory(
            "cloudmesh.ai.vpn.linux_factory", "get_linux_strategy_class"
        )(provider)
    
    if os_is_mac():
        return _load_factory(
            "cloudmesh.ai.vpn.mac_factory", "get_mac_strategy_class"
        )(provider)
    
    raise NotImplementedError("Operating System not supported")
