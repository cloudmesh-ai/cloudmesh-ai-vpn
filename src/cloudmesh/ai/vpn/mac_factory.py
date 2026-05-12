from typing import Optional, Type

from cloudmesh.ai.vpn.strategies.base import VpnOSStrategy
from cloudmesh.ai.vpn.strategies.mac_cisco import MacCiscoStrategy
from cloudmesh.ai.vpn.strategies.mac_openconnect_decrypted import (
    MacOpenConnectDecryptedStrategy,
)
from cloudmesh.ai.vpn.strategies.mac_openconnect_keychain import (
    MacOpenConnectKeychainStrategy,
)
from cloudmesh.ai.vpn.strategies.mac_openconnect_pw import MacOpenConnectPwStrategy


MAC_STRATEGIES = {
    "openconnect-decrypted": MacOpenConnectDecryptedStrategy,
    "openconnect-pw": MacOpenConnectPwStrategy,
    "openconnect-keychain": MacOpenConnectKeychainStrategy,
    "cisco": MacCiscoStrategy,
}


def get_mac_strategy_class(provider: Optional[str] = None) -> Type[VpnOSStrategy]:
    """Return the macOS VPN strategy class for the requested provider."""
    provider_key = provider if provider else "openconnect-decrypted"
    return MAC_STRATEGIES.get(provider_key, MacOpenConnectDecryptedStrategy)
