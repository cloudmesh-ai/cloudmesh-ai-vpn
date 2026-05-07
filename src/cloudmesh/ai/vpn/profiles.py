import os
from typing import Any, Dict, Optional
from cloudmesh.ai.common.io import console, path_expand, load_yaml, dump_yaml

PROFILES_FILE = path_expand("~/.cloudmesh/vpn/profiles.yaml")

def load_profiles() -> Dict[str, Any]:
    """Load VPN profiles from the YAML file."""
    if not os.path.exists(PROFILES_FILE):
        return {}
    
    try:
        data = load_yaml(PROFILES_FILE)
        return data.get("profiles", {}) if data else {}
    except Exception as e:
        console.error(f"Failed to load profiles: {e}")
        return {}

def save_profiles(profiles: Dict[str, Any]) -> None:
    """Save VPN profiles to the YAML file."""
    try:
        os.makedirs(os.path.dirname(PROFILES_FILE), exist_ok=True)
        dump_yaml({"profiles": profiles}, PROFILES_FILE)
    except Exception as e:
        console.error(f"Failed to save profiles: {e}")

def add_profile(name: str, service: str, **kwargs) -> bool:
    """Add or update a VPN profile.
    
    Args:
        name: Name of the profile.
        service: The VPN service to use.
        **kwargs: Arbitrary attributes to override organization defaults (e.g., host, provider, nosplit).
    """
    profiles = load_profiles()
    profile_data = {"service": service}
    profile_data.update(kwargs)
    
    profiles[name] = profile_data
    save_profiles(profiles)
    return True

def remove_profile(name: str) -> bool:
    """Remove a VPN profile."""
    profiles = load_profiles()
    if name in profiles:
        del profiles[name]
        save_profiles(profiles)
        return True
    return False

def get_profile(name: str) -> Optional[Dict[str, Any]]:
    """Get a specific VPN profile."""
    profiles = load_profiles()
    return profiles.get(name)