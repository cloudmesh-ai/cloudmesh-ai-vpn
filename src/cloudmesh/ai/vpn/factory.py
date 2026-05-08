import os
from typing import Optional, Type
from cloudmesh.ai.common.sys import os_is_linux, os_is_mac, os_is_windows
from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.vpn.strategies.windows import WindowsVpnStrategy
from cloudmesh.ai.vpn.strategies.linux import LinuxVpnStrategy
from cloudmesh.ai.vpn.strategies.mac_openconnect_decrypted import MacOpenConnectDecryptedStrategy
from cloudmesh.ai.vpn.strategies.mac_openconnect_pw import MacOpenConnectPwStrategy
from cloudmesh.ai.vpn.strategies.mac_openconnect_keychain import MacOpenConnectKeychainStrategy
from cloudmesh.ai.vpn.strategies.mac_cisco import MacCiscoStrategy
from cloudmesh.ai.vpn.strategies.mock import MockVpnStrategy

def get_vpn_strategy_class(provider: Optional[str] = None) -> Type[VpnOSStrategy]:
    """
    Factory function to return the appropriate VPN strategy class based on OS and provider.
    """
    if os.environ.get("VPN_MOCK") == "1":
        return MockVpnStrategy
    
    if os_is_windows():
        return WindowsVpnStrategy
    
    if os_is_linux():
        return LinuxVpnStrategy
    
    if os_is_mac():
        mac_strategies = {
            "openconnect-decrypted": MacOpenConnectDecryptedStrategy,
            "openconnect-pw": MacOpenConnectPwStrategy,
            "openconnect-keychain": MacOpenConnectKeychainStrategy,
            "cisco": MacCiscoStrategy,
        }
        provider_key = provider if provider else "openconnect-decrypted"
        return mac_strategies.get(provider_key, MacOpenConnectDecryptedStrategy)
    
    raise NotImplementedError("Operating System not supported")