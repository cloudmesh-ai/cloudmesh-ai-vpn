import os
import yaml
from typing import Any, Dict, Optional
from cloudmesh.ai.common.io import Console

PROFILES_FILE = os.path.expanduser("~/.cloudmesh/vpn/profiles.yaml")

def load_profiles() -> Dict[str, Any]:
    """Load VPN profiles from the YAML file."""
    if not os.path.exists(PROFILES_FILE):
        return {}
    
    try:
        with open(PROFILES_FILE, "r") as f:
            data = yaml.safe_load(f)
            return data.get("profiles", {}) if data else {}
    except Exception as e:
        Console.error(f"Failed to load profiles: {e}")
        return {}

def save_profiles(profiles: Dict[str, Any]) -> None:
    """Save VPN profiles to the YAML file."""
    try:
        os.makedirs(os.path.dirname(PROFILES_FILE), exist_ok=True)
        with open(PROFILES_FILE, "w") as f:
            yaml.dump({"profiles": profiles}, f)
    except Exception as e:
        Console.error(f"Failed to save profiles: {e}")

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