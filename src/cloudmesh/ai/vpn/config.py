import os
from typing import Any, Dict, Optional, List
from cloudmesh.ai.common.io import load_yaml, console

class VpnConfig:
    """
    Handles flexible configuration for VPN connections.
    Supports loading from multiple sources with a specific override hierarchy:
    Default < System < User < Project < Profile < Environment
    """

    def __init__(self, service: Optional[str] = None, profile_name: Optional[str] = None):
        self.service = service or "uva"
        self.profile_name = profile_name
        self.config: Dict[str, Any] = {}
        self._load_all_configs()

    def _load_yaml_file(self, path: str) -> Dict[str, Any]:
        """Helper to load YAML and extract the vpn section."""
        expanded_path = os.path.expanduser(path)
        if os.path.exists(expanded_path):
            try:
                data = load_yaml(expanded_path)
                # Support both nested 'cloudmesh.vpn' and flat structures
                if isinstance(data, dict):
                    return data.get("cloudmesh", {}).get("vpn", data.get("vpn", {}))
            except Exception as e:
                console.warning(f"Could not load config file {path}: {e}")
        return {}

    def _load_all_configs(self) -> None:
        """Loads configurations from all supported sources in order of priority."""
        # 1. System-wide config
        system_config = self._load_yaml_file("/etc/cloudmesh/vpn.yaml")
        
        # 2. User-wide config
        user_config = self._load_yaml_file("~/.cloudmesh/vpn.yaml")
        
        # 3. Project-specific config (the original organizations.yaml)
        project_file = os.path.join(os.path.dirname(__file__), "organizations.yaml")
        project_config = self._load_yaml_file(project_file)

        # Merge global organization settings
        # We want the specific service config if available, otherwise defaults
        merged_orgs = {}
        for cfg in [system_config, user_config, project_config]:
            merged_orgs.update(cfg)

        # Get the specific configuration for the requested service
        service_key = self.service.lower()
        service_defaults = merged_orgs.get(service_key, {})

        # 4. Profile overrides
        profile_config = {}
        if self.profile_name:
            from cloudmesh.ai.vpn import profiles
            profile = profiles.get_profile(self.profile_name)
            if profile:
                profile_config = profile
                # If profile specifies a different service, update it
                if "service" in profile:
                    self.service = profile["service"]
                    service_defaults = merged_orgs.get(self.service.lower(), {})

        # Final Merge Hierarchy
        self.config = service_defaults.copy()
        self.config.update(profile_config)
        
        # 5. Environment Variable Overrides
        # Example: VPN_HOST=vpn.example.com
        for key in self.config.keys():
            env_key = f"VPN_{key.upper()}"
            env_val = os.environ.get(env_key)
            if env_val:
                # Try to cast to original type if possible
                original_val = self.config[key]
                if isinstance(original_val, bool):
                    self.config[key] = env_val.lower() in ("true", "1", "yes")
                elif isinstance(original_val, int):
                    try:
                        self.config[key] = int(env_val)
                    except ValueError:
                        pass
                else:
                    self.config[key] = env_val

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value."""
        return self.config.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.config[key]

    def __contains__(self, key: str) -> bool:
        return key in self.config

    def __repr__(self) -> str:
        return f"VpnConfig(service={self.service}, profile={self.profile_name}, config={self.config})"