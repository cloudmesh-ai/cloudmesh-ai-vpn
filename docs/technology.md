# Cloudmesh VPN: Technical Implementation & Installation Guide

This guide provides the complete technical specifications for the `cms vpn connect` and `disconnect` operations across macOS, Linux, and Windows, specifically for the **UVA Anywhere** service.

---

## 1. Installation Requirements

### Common Requirements (All OS)
- **Python 3.x**
- **Cloudmesh VPN Package**: `pip install .` from the project root.
- **Keyring**: Used for secure storage of passwords.

### OS-Specific Dependencies
| OS | Required Binaries | Installation Command | Special Files/Requirements |
| :--- | :--- | :--- | :--- |
| **macOS** | `openconnect`, `vpn-slice` | `brew install openconnect vpn-slice` | `~/.ssh/uva/decrypted_user.pem` |
| **Linux** | `openconnect`, `vpn-slice` | `sudo apt install openconnect` / `pip install vpn-slice` | `~/.ssh/uva/` (`usher.cer`, `user.key`, `user.crt`) |
| **Windows** | `openconnect.exe` | `choco install openconnect-gui` | **Run Terminal as Administrator** |

---

## 2. Technical Solution: Connect & Disconnect

### 🍎 macOS (Strategy: `MacOpenConnectDecrypted`)
**Connect Logic:**
1. **Sudo Warm-up**: Runs `sudo -v` to cache admin credentials.
2. **Backgrounding**: Uses `subprocess.Popen` and `os.setpgid(pid, 0)` to isolate the process group, ensuring the VPN stays alive after the CLI exits.
3. **Auth**: Pipes password via `stdin` if provided.

**Precise Command:**
```bash
sudo /opt/homebrew/bin/openconnect --protocol=anyconnect -u thf2bn -c /Users/grey/.ssh/uva/decrypted_user.pem --script='/opt/homebrew/bin/vpn-slice -v rivanna.hpc.virginia.edu 128.143.0.0/16 137.54.0.0/16' uva-anywhere-1.itc.virginia.edu
```

**Disconnect Logic:**
- Sends `SIGINT` (Signal 2) to the tracked PID: `os.kill(pid, 2)`.
- Fallback: `sudo pkill -SIGINT openconnect` and `sudo pkill vpn-slice`.

---

### 🐧 Linux (Strategy: `LinuxVpnStrategy`)
**Connect Logic:**
1. **Environment Detection**: Checks for `/.dockerenv` to toggle between Host and Container mode.
2. **Execution**: Uses `os.system()` (blocking call) and waits for `is_enabled()` to return True.
3. **Auth**: Uses a 3-file certificate set for authentication.

**Precise Command (Host):**
```bash
sudo openconnect -b -v --protocol=anyconnect --cafile="~/.ssh/uva/usher.cer" --sslkey="~/.ssh/uva/user.key" --certificate="~/.ssh/uva/user.crt" uva-anywhere-1.itc.virginia.edu
```

**Precise Command (Docker):**
```bash
openconnect -b -v --protocol=anyconnect --cafile="/root/.ssh/uva/usher.cer" --sslkey="/root/.ssh/uva/user.key" --certificate="/root/.ssh/uva/user.crt" -m 1290 uva-anywhere-1.itc.virginia.edu --script='vpn-slice --prevent-idle-timeout rivanna.hpc.virginia.edu biihead1.bii.virginia.edu biihead2.bii.virginia.edu'
```

**Disconnect Logic:**
- Executes `sudo pkill -SIGINT openconnect`.

---

### 🪟 Windows (Strategy: `WindowsVpnStrategy`)
**Connect Logic:**
1. **Admin Check**: Verifies Administrator privileges via `pyuac`.
2. **Conflict Resolution**: Force-kills Cisco processes (`taskkill /F`) and resets the `csc_vpnagent` service via `net stop/start`.
3. **Routing**: Injects environment variables into the process for the JScript helper.

**Environment Variables Injected:**
- `VPN_DOMAIN=virginia.edu`
- `CISCO_SPLIT_INC=2`
- `CISCO_SPLIT_INC_1_ADDR=rivanna.hpc.virginia.edu 128.143.0.0/16 137.54.0.0/16`
- `CISCO_SPLIT_INC_1_MASK=255.255.0.0`
- `CISCO_SPLIT_INC_1_MASKLEN=16`

**Precise Command:**
```powershell
openconnect.exe uva-anywhere-1.itc.virginia.edu --user=thf2bn --passwd-on-stdin --script="C:\...\bin\split-script-win.js"
```
*(Password and optional "push" for 2FA are piped into stdin)*.

**Disconnect Logic:**
- **Process**: `psutil` terminates `openconnect.exe`.
- **DNS Cleanup**: Runs a PowerShell command to remove NRPT rules:
  `Get-DnsClientNrptRule | Where-Object { $_.Namespace -eq '.virginia.edu' } | Remove-DnsClientNrptRule -Force`

---

## 3. YAML Configuration Examples

### Password Authentication
```yaml
    uva:
      username: thf2bn
      auth: pw
      name: UVA Anywhere
      host: uva-anywhere-1.itc.virginia.edu
      user: true
      2fa: false
      group: false
      ip: 
        - rivanna.hpc.virginia.edu 
        - 128.143.0.0/16 
        - 137.54.0.0/16
      domain: virginia.edu
```

### Certificate Authentication
```yaml
    uva:
      username: thf2bn
      auth: cert
      cert: ~/.ssh/uva/decrypted_user.pem
      name: UVA Anywhere
      host: uva-anywhere-1.itc.virginia.edu
      user: false
      2fa: false
      group: false
      ip: 
        - rivanna.hpc.virginia.edu 
        - 128.143.0.0/16 
        - 137.54.0.0/16
      domain: virginia.edu


# APPENDIX

### 2. Handling "Zombie" Processes & Orphanage

The macOS implementation reveals a clever trick for backgrounding processes. By using `os.setpgid(proc.pid, 0)`, the program creates a new process group.

- __The Problem__: Normally, when a parent process (the `cms` CLI) dies, the OS sends a `SIGHUP` to all children, which would kill the VPN.
- __The Solution__: By moving the VPN into its own group, it becomes "orphaned" and is adopted by the system init process, allowing it to persist in the background while the CLI exits.

### 4. The "Sudo Warm-up" Pattern

To avoid the "interactive prompt" problem (where a program hangs because it's waiting for a password in a hidden terminal), the code uses `sudo -v` (on macOS) or `Sudo.password()` (on Linux).

- This updates the user's cached credentials in the system's sudoers timestamp.
- This ensures that the subsequent `sudo openconnect` command runs instantly without pausing for user input.

### . Docker-Aware Networking

The Linux strategy shows a sophisticated approach to containerization. It doesn't just check if it's in Docker; it changes the __MTU (Maximum Transmission Unit)__ to `1290`.

- This is a common fix for "VPN-in-Docker" scenarios where the overhead of the Docker network bridge plus the VPN encapsulation exceeds the standard 1500-byte packet limit, which would otherwise cause the connection to hang or drop packets.

### . The "Watch" System (Observability)

The `watch()` method provides a high-level health check by gathering "evidence" from three different sources:

- __Process List__: Checks if `openconnect` and `vpn-slice` are actually running.
- __Command Line Inspection__: Runs `ps aux` and uses regex to extract the actual IP ranges being routed by `vpn-slice` to verify they match the config.
- __Kernel Routing Table__: Runs `netstat -rn` to verify that the OS kernel actually has the routes active.

This multi-layered verification en
