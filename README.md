# Cloudmesh AI VPN Extension

**Authors**:
*   **Gregor von Laszewski** ([laszewski@gmail.com](mailto:laszewski@gmail.com))
*   **JP Fleischer**

This extension provides professional tools to manage VPN connections, profiles, and keys, specifically tailored for UVA Anywhere VPN and other compatible providers. It focuses on a "zero-config" experience and high visibility into the connection state.

## Installation

### 🍎 macOS
**Recommended: Using pipx**
For the best experience with CLI tools, use `pipx` to install `cloudmesh-ai-vpn` in an isolated environment.
```bash
pipx install cloudmesh-ai-vpn
```
*To install from a local directory: `pipx install .`*

**Using pip**
```bash
pip install cloudmesh-ai-vpn
```
*To install from a local directory: `pip install .`*

**Dependencies**: Ensure `openconnect` and `vpn-slice` are installed via Homebrew:
```bash
brew install openconnect vpn-slice
```

### 🐧 Linux
**Recommended: Using pipx**
```bash
pipx install cloudmesh-ai-vpn
```
*To install from a local directory: `pipx install .`*

**Using pip**
```bash
pip install cloudmesh-ai-vpn
```

**Dependencies**: Install `openconnect` and `vpn-slice` using your package manager (e.g., `apt` or `dnf`).

### 🪟 Windows
**Using pip**
```powershell
pip install cloudmesh-ai-vpn
```

**⚠️ Important Warning**: The author does not have access to a Windows machine. Consequently, Windows support has not been tested and is **not guaranteed to work**. If you encounter issues, please report them in the issue tracker.

**Dependencies & Chocolatey**: 
This extension can attempt to manage Windows dependencies using **Chocolatey**. You can use the `--choco` flag when connecting to trigger dependency checks and installation:
```powershell
cme vpn connect --choco
```
If you prefer manual installation, ensure you have a compatible OpenConnect client installed on your system.

## Usage Examples

### Connection Management

**1. Connect to the default VPN service**
```bash
cme vpn connect
```
> ```text
> Password: ───────
> ⠼ Checking dependencies...
> ⠴ Warming up sudo...
> ⠇ Launching OpenConnect...
> ✓ Connected to uva
> ```

**2. Connect with a specific service and provider**
```bash
cme vpn connect --service uva-hpc --provider openconnect-keychain
```
> ```text
> ⠼ Checking dependencies...
> ⠴ Warming up sudo...
> ⠇ Launching OpenConnect (Keychain)...
> ✓ Connected to uva-hpc
> ```

**3. Disconnect from the VPN**
```bash
cme vpn disconnect
```
> ```text
> ℹ Disconnecting OpenConnect...
> ✓ Successfully disconnected from VPN.
> ```

### Status and Information

**4. Check if the VPN is connected**
```bash
cme vpn status
```
> ```text
> True
> ```

**5. Get current location and connection info**
```bash
cme vpn info
```
> ```text
> ┌──────────────────────────────────────────────────────────┐
> │                    IP Information                        │
> ├────────────────────┬─────────────────────────────────────┤
> │ Field              │ Value                               │
> ├────────────────────┼─────────────────────────────────────┤
> │ ip                 │ 128.118.x.x                         │
> │ city               │ Charlottesville                     │
> │ region             │ Virginia                            │
> │ country            │ United States                       │
> └────────────────────┴─────────────────────────────────────┘
> ```

### Configuration and Maintenance

**6. Reset VPN credentials**
```bash
cme vpn reset --service uva
```
> ```text
> ✓ Successfully reset routes for uva
> ```

**7. Manage VPN profiles**
```bash
cme vpn profile list
```
> ```text
> Default: {'service': 'uva'}
> Work-Remote: {'service': 'uva-remote'}
> ```

**8. Manage Keychain passphrases**
```bash
cme vpn keychain
```
> ```text
> ℹ Searching Keychain for service: uva-key-pass...
> ✓ Passphrase securely retrieved from macOS Keychain.
> ```

**9. Monitor connection**
```bash
cme vpn watch 10
```
*(See Appendix for detailed `vpn watch` output)*

## Command Reference

| Command | Description | Options |
| :--- | :--- | :--- |
| `connect` / `+` | Connects to the VPN. | `--service`, `--timeout`, `--provider`, `--profile`, `--nosplit` |
| `disconnect` / `-` | Disconnects from the VPN. | `-v` (debug) |
| `status` | Returns `True` if connected, `False` otherwise. | `-v` (debug) |
| `info` | Prints location and IP information. | `-v` (debug) |
| `reset` | Clears credentials/routes for the service. | `--service` |
| `watch` | Monitors the connection at an interval. | `[INTERVAL]`, `--count` |
| `keychain` | Manages passphrases in macOS Keychain. | `[remove]`, `--service` |
| `profile` | Manages user-specific connection profiles. | `[add\|remove\|list]`, `--name`, `--service` |

---

## Appendix: Advanced Functionality

### 🚀 Granular Progress Reporting
The extension now features a rich CLI interface that provides real-time feedback during the connection process. Instead of a hanging terminal, you will see a dynamic spinner and status updates:
*   **Dependency Checks**: Verifies `openconnect` and `vpn-slice` are installed.
*   **Sudo Warm-up**: Handles system authentication before the UI starts to prevent prompt interference.
*   **Provider-Specific Logs**: Clearly indicates which authentication method (Keychain, Password, or Decrypted Cert) is being used.

### 🛠 macOS Provider Guide
Depending on your security preference and available files, you can choose from several providers via the `--provider` flag:

| Provider | Use Case | Requirement |
| :--- | :--- | :--- |
| `openconnect-decrypted` | Fastest, no passphrase prompt. | Decrypted `.pem` file in `~/.ssh/uva/` |
| `openconnect-keychain` | Secure and seamless. | Passphrase stored in macOS Keychain |
| `openconnect-pw` | Standard authentication. | Username and Password |
| `mac-cisco` | Legacy support. | Cisco AnyConnect Client installed |

### 🔍 Connection Monitoring (`vpn watch`)
The `vpn watch` command provides a high-fidelity view of your tunnel's health. Unlike simple status checks, it performs a multi-layered verification:
1.  **Process Check**: Verifies that `openconnect` and `vpn-slice` processes are active.
2.  **Route Verification**: Executes `netstat -rn` to confirm that the specific IP ranges for your organization are actually present in the system routing table.
3.  **Dynamic Feedback**: Updates in real-time, allowing you to see exactly when a tunnel drops or a route is removed.

**Example Output:**
```text
┌──────────────────────────────────────────────────────────────┐
│ VPN Watch | Iteration: 1 | Service: uva                      │
├────────────────────┬─────────────────────────────────────────┤
│ Category           │ Status                                  │
├────────────────────┼─────────────────────────────────────────┤
│ Process            │ 'vpn-slice' is running (PIDs: 1234)      │
│ Process            │ 'openconnect' is running (PIDs: 5678)    │
│ OpenConnect        │ Routes configured: 128.143.0.0/16        │
│ Routing Table      │ Route to 128.143.0.0/16 found (netstat)  │
└────────────────────┴─────────────────────────────────────────┘
```

### 🌐 Split-Tunneling with `vpn-slice`
By default, this extension implements **Split-Tunneling** using `vpn-slice`. This is critical for maintaining performance and accessibility.

*   **Split-Tunnel (Default)**: Only traffic destined for the VPN's specific IP ranges (e.g., UVA internal networks) is routed through the tunnel. Your general internet traffic (web browsing, streaming, etc.) continues to use your local gateway.
*   **Full-Tunnel (`--nosplit`)**: All system traffic is routed through the VPN. This is useful for high-security environments but will significantly increase latency for non-VPN traffic and may break local network access.
*   **How it works**: The extension identifies the required IP ranges from the organization config and instructs `vpn-slice` to create precise routing entries in your OS.

### 📂 Zero-Config File Structure
For the `openconnect-decrypted` and `openconnect-keychain` providers to work without extra flags, place your certificates in the following default location:

```text
~/.ssh/uva/
├── user.crt          # Public Certificate
├── user.key          # Private Key
└── decrypted_user.pem # Decrypted PEM (for decrypted provider)
```

### 🎓 UVA Custom Configuration
If you are a UVA user and need to override the default organization settings, you can use a custom YAML configuration file.

**Customizing your Identity**:
To ensure the VPN connects with your specific credentials, locate the `organizations.yaml` file (or your custom override) and update the `username` field:

```yaml
uva:
  username: "your_computing_id"  # <--- Change this to your UVA Computing ID
  auth: cert
  name: UVA Anywhere
  host: uva-anywhere-1.itc.virginia.edu
  user: false
  2fa: false
  group: false
  keychain: true
  cert:
    - ~/.ssh/uva/user.pem
  ip: 
    - rivanna.hpc.virginia.edu 
    - 128.143.0.0/16 
    - 137.54.0.0/16
    - 199.111.0.0/16
    - 199.111.160.0/19
    - 199.111.192.0/18
  domain: virginia.edu
  connection_check:
    - University of Virginia
    - UVA
```

By updating this value, the extension will automatically use your identity across all connection attempts without requiring manual flags.

