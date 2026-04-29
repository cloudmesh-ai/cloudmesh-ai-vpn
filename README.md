# Cloudmesh AI VPN Extension

This extension provides tools to manage VPN connections, profiles, and keys, specifically tailored for UVA Anywhere VPN and other compatible providers.

## Installation

### Recommended: Using pipx
For the best experience with CLI tools, use `pipx` to install `cloudmesh-ai-vpn` in an isolated environment.

``` bash
pipx install cloudmesh-ai-vpn
```

To install from a local directory:
``` bash
pipx install .
```

### Using pip
If you prefer a standard installation in your current environment:

``` bash
pip install cloudmesh-ai-vpn
```

To install from a local directory:
``` bash
pip install .
```

## Usage Examples

### Connection Management
1. **Connect to the default VPN service:**
   `cme vpn connect` or `cme vpn +`

2. **Connect with a specific service and provider:**
   `cme vpn connect --service my-service --provider openconnect`

3. **Disconnect from the VPN:**
   `cme vpn disconnect` or `cme vpn -`

### Status and Information
4. **Check if the VPN is connected:**
   `cme vpn status`

5. **Get current location and connection info:**
   `cme vpn info`

### Configuration and Maintenance
6. **Reset VPN credentials:**
   `cme vpn reset --service my-service`

7. **Manage VPN profiles:**
   - List profiles: `cme vpn profile list`
   - Add a profile: `cme vpn profile add`
   - Remove a profile: `cme vpn profile remove`

8. **Manage Keychain passphrases:**
   - Add passphrase: `cme vpn keychain`
   - Remove passphrase: `cme vpn keychain remove`

9. **Monitor connection:**
   `cme vpn watch 30` (checks every 30 seconds)

## Command Reference

| Command | Description |
| :--- | :--- |
| `connect` / `+` | Connects to the VPN. Supports `--service`, `--timeout`, `--provider`, and `--profile`. |
| `disconnect` / `-` | Disconnects from the VPN. |
| `status` | Returns `True` if connected, `False` otherwise. |
| `info` | Prints location and IP information obtained via VPN. |
| `reset` | Clears credentials for the specified service. |
| `watch` | Monitors the connection at a specified interval. |
| `keychain` | Manages VPN private key passphrases in the macOS Keychain. |
| `profile` | Manages user-specific connection profiles. |