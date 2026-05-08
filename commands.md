###########################
# LINUX
###########################

 sudo openconnect -vvv --protocol=anyconnect   -u thf2bn   -c decrypted_user.pem   --script='/home/green/.pyenv/shims/vpn-slice -v rivanna.hpc.virginia.edu 128.143.0.0/16 137.54.0.0/16'   uva-anywhere-1.itc.virginia.edu

n Linux, the implementation is significantly different from macOS, primarily because it handles two distinct environments: Standard Linux and Docker Containers.

1. The "Connect" Logic: Environment-Based Execution
The LinuxVpnStrategy detects if it is running inside a Docker container (by checking for /.dockerenv or docker in /proc/self/cgroup) and changes its behavior accordingly:

Standard Linux (Host):

Sudo Warm-up: Like macOS, it calls Sudo.password() to cache credentials.
Command: It executes a sudo openconnect command using a set of three specific certificate files (usher.cer, user.key, user.crt) located in ~/.ssh/uva/.
Execution: It uses os.system(command), which is a blocking call. It redirects output to /dev/null to keep the console clean.
Verification: After executing, it enters a while loop, sleeping for 1 second and calling is_enabled() until the VPN is confirmed active.
Docker Container:

No Sudo: It runs openconnect without sudo (assuming the container is already privileged).
Split Tunneling: It explicitly adds a --script argument calling vpn-slice with a specific set of targets (rivanna.hpc.virginia.edu, etc.) and the --prevent-idle-timeout flag.
MTU Setting: It adds -m 1290 to the command to optimize the Maximum Transmission Unit for containerized networking.
2. The "Disconnect" Logic: Signal-Based Termination
Linux does not track the PID of the process in the same way the macOS strategy does. Instead, it relies on the pkill utility:

Standard Linux: It executes sudo pkill -SIGINT openconnect. This sends a "Interrupt" signal to all processes named openconnect, triggering a graceful shutdown.
Docker Container: It executes pkill -SIGINT openconnect followed by pkill -SIGINT vpn-slice. Since it's in a container, it doesn't use sudo and explicitly ensures the vpn-slice helper process is also killed.
Summary Comparison: macOS vs. Linux
Feature	macOS Technical Solution	Linux Technical Solution
Persistence	Popen + os.setpgid (Process Group)	os.system (Blocking/Foreground)
Sudo	sudo -v $\rightarrow$ sudo openconnect	Sudo.password() $\rightarrow$ sudo openconnect
Auth	Decrypted PEM file + Password	3-file Cert set (.cer, .key, .crt)
Disconnect	PID-based os.kill $\rightarrow$ pkill	Direct pkill -SIGINT
Container	Not specifically handled	Specialized MTU and vpn-slice flags



###########################
# MAC
###########################

sudo /opt/homebrew/bin/openconnect --protocol=anyconnect -u thf2bn -c /Users/grey/.ssh/uva/decrypted_user.pem --script='/opt/homebrew/bin/vpn-slice -v rivanna.hpc.virginia.edu 128.143.0.0/16 137.54.0.0/16' uva-anywhere-1.itc.virginia.edu
```
*Note: If a password were provided in the credentials, `--passwd-on-stdin` would be appended to the end of the command, and the password would be piped into the process's stdin.*


PASS="YOUR_PASSWORD" sudo -E openconnect --passwd-on-stdin [ARGS] <<< "$PASS"


On macOS, the technical challenge is that openconnect is a long-running foreground process that requires root privileges (sudo) and interactive input for passwords. The program solves this using several specific system-level techniques:

1. The "Connect" Logic: Background Persistence
To prevent the VPN from closing as soon as the cms command finishes, the program does not use a simple subprocess.run. Instead, it uses a combination of:

subprocess.Popen: It launches openconnect as a separate process.
Process Group Isolation (os.setpgid): After launching, the program calls os.setpgid(proc.pid, 0). This moves the VPN process into its own process group. This is critical because it prevents the VPN from receiving a SIGHUP (hangup signal) when the parent cms process exits, allowing the VPN to stay alive in the background.
Sudo Caching (sudo -v): To avoid the program hanging while waiting for a password prompt that the user can't see, it runs sudo -v first. This "warms up" the sudo timestamp, caching the administrator's credentials so the subsequent openconnect command can run with root privileges without prompting.
Stdin Piping: For password authentication, it uses stdin=subprocess.PIPE to programmatically write the password and a newline (\n) directly into the openconnect process.
2. The "Disconnect" Logic: Targeted Termination
Since the VPN is running as a background process with root privileges, the program cannot simply "stop" it. It uses a two-tier approach:

PID Tracking: The strategy attempts to store the _pid of the openconnect process. If the PID is known, it sends a SIGINT (Signal 2, equivalent to Ctrl+C) using os.kill(self._pid, 2). This allows openconnect to shut down gracefully and clean up its own routing table.
Fallback Pkill: If the PID is lost or the process is unresponsive, it falls back to a "nuclear" option using the shell: sudo pkill -SIGINT openconnect sudo pkill vpn-slice This ensures all related VPN processes are terminated regardless of whether the program tracked their PIDs.
3. Routing Cleanup (The "Reset" Logic)
Because vpn-slice modifies the system routing table, a crash or forced kill can leave "stale" routes. The program solves this by:

Reading the ip ranges from organizations.yaml.
Executing sudo route delete -net <target> for every range associated with the service.
It tries deleting as a network first, and if that fails, it tries deleting as a host route to ensure the system network state is completely restored.
Summary Table
Action	Technical Solution	Purpose
Privileges	sudo -v $\rightarrow$ sudo openconnect	Avoid interactive sudo prompts
Persistence	Popen + os.setpgid	Keep VPN alive after cms exits
Auth	stdin.write(pw + "\n")	Automate password entry
Stop	os.kill(pid, 2) $\rightarrow$ pkill	Graceful shutdown of background process
Cleanup	sudo route delete

###########################
# WINDOWS 
###########################

For a connection to UVA Anywhere on Windows using password authentication, here are the precise commands and environment variables as they would be executed by the tool.

1. Pre-Connection Cleanup (Executed sequentially)
These are run to ensure no Cisco AnyConnect processes interfere with OpenConnect:


taskkill /im vpnagent.exe /F
taskkill /im vpncli.exe /F
net stop csc_vpnagent
net start csc_vpnagent
taskkill /im csc_ui.exe /F
2. Environment Variables
The following variables are injected into the process environment before the VPN command is launched. These are critical because the Windows split-tunneling script (split-script-win.js) reads these instead of command-line arguments:

Variable	Value
VPN_DOMAIN	virginia.edu
CISCO_SPLIT_INC	2
CISCO_SPLIT_INC_1_ADDR	rivanna.hpc.virginia.edu 128.143.0.0/16 137.54.0.0/16
CISCO_SPLIT_INC_1_MASK	255.255.0.0
CISCO_SPLIT_INC_1_MASKLEN	16
3. The VPN Connection Command
The final command executed (assuming openconnect.exe is in the path) is:


openconnect.exe uva-anywhere-1.itc.virginia.edu --user=thf2bn --passwd-on-stdin --script="C:\Users\grey\work\OLD\cloudmesh-vpn\src\cloudmesh\vpn\bin\split-script-win.js"
4. Standard Input (Stdin) Sequence
Because --passwd-on-stdin is used, the tool pipes the following data into the process:

YOUR_PASSWORD\n
(If 2fa: true is set in YAML): push\n
Summary of the full Windows flow:

Admin Check: Verifies terminal is running as Administrator.
Cleanup: Kills Cisco processes and restarts the agent.
Env Setup: Sets the 5 CISCO_SPLIT and VPN_DOMAIN variables.
Launch: Starts openconnect.exe with the host, user, and script path.
Auth: Pipes the password (and "push" for Duo) into the process.

lan Created

Windows handling is the most complex of the three because it has to deal with the official Cisco AnyConnect client, which often locks the VPN agent and conflicts with OpenConnect.

Here is the technical breakdown of how connect and disconnect are solved on Windows:

1. The "Connect" Logic: Conflict Resolution & Environment Injection
Unlike macOS and Linux, Windows cannot simply launch openconnect.exe and expect it to work if the official Cisco client is installed.

Privilege Enforcement: The program uses the pyuac library to check isUserAdmin(). If the terminal isn't running as Administrator, it exits immediately because modifying network routes on Windows requires elevated privileges.
The "Cisco Kill" Sequence: To prevent the official Cisco agent from blocking the connection, the program executes a mandatory cleanup:
Force Kill: It uses taskkill /F on vpnagent.exe, vpncli.exe, and csc_ui.exe.
Service Reset: It runs net stop csc_vpnagent followed by net start csc_vpnagent. This resets the system service into a state where OpenConnect can take control.
Environment-Based Routing: Windows doesn't support the same --script argument style as Unix. Instead, the program:
Launches a JavaScript helper (split-script-win.js).
Injects Environment Variables: It passes the routing targets (IP ranges and domains) as environment variables (e.g., CISCO_SPLIT_INC_1_ADDR). The JS script reads these variables to configure the Windows routing table.
Auth & 2FA: It uses subprocess.Popen with stdin=subprocess.PIPE. It writes the password, and if 2fa: true is set in the YAML, it automatically writes "push\n" to trigger a Duo push notification.
2. The "Disconnect" Logic: Process & Route Cleanup
Disconnecting on Windows requires cleaning up both the process and the system's DNS/Routing state:

Process Termination: It uses psutil to find any process named openconnect.exe and calls .terminate(). If the process doesn't exit within 3 seconds, it calls .kill() to force it closed.
NRPT Rule Removal: This is a Windows-specific step. The "Name Resolution Policy Table" (NRPT) can keep DNS entries for the VPN active even after the tunnel is closed. The program executes a PowerShell command to find and remove these rules: Get-DnsClientNrptRule | Where-Object { ... } | Remove-DnsClientNrptRule -Force
Summary Comparison: Windows vs. Unix
Feature	Windows Technical Solution	Unix (macOS/Linux) Solution
Privileges	pyuac (Admin check)	sudo -v / Sudo.password()
Conflict Mgmt	taskkill + net stop/start	Not required
Routing	Env Vars $\rightarrow$ split-script-win.js	--script $\rightarrow$ vpn-slice
Persistence	start_new_session=True	os.setpgid (macOS) / Blocking (Linux)
Cleanup	PowerShell Remove-DnsClientNrptRule	sudo route delete

####################
# INSTALL
####################

o install and run this VPN tool on all three operating systems, you need both the Python environment and the system-level binaries that the program calls.

1. Common Requirements (All OS)
Regardless of the OS, you need:

Python 3.x installed.
The Python Package: Install the cloudmesh-vpn package (usually via pip install . from the project root).
Keyring: The tool uses the keyring library to store passwords securely in the OS vault.
2. OS-Specific System Dependencies
macOS
The tool relies on Homebrew for its binaries.

OpenConnect: brew install openconnect
VPN-Slice: brew install vpn-slice
Certificates: If using the openconnect-decrypted provider, you must place your decrypted certificate at: ~/.ssh/uva/decrypted_user.pem
Linux
Depending on your distribution (Ubuntu/Debian example):

OpenConnect: sudo apt-get install openconnect
VPN-Slice: Install via pip: pip install vpn-slice
Certificates: You must have the following three files in ~/.ssh/uva/:
usher.cer (CA Certificate)
user.key (Private Key)
user.crt (Client Certificate)
Windows
Windows requires a few more steps due to the way it handles binaries and privileges.

Chocolatey: The tool has a --choco flag to automate this, but manually you need Chocolatey installed.
OpenConnect: choco install openconnect-gui (or the standalone binary).
Node.js: Required to run the split-script-win.js helper.
Privileges: You must run your terminal (PowerShell or CMD) as Administrator.
3. Installation Summary Table
Component	macOS	Linux	Windows
Package Mgr	Homebrew	apt / yum / pip	Chocolatey
VPN Binary	openconnect	openconnect	openconnect.exe
Routing Tool	vpn-slice	vpn-slice	node.js (for .js script)
Auth Files	decrypted_user.pem	.cer, .key, .crt	System Keys / Password
Privileges	sudo	sudo	Run as Administrator
Quick Start Command
Once the system dependencies are installed, you can connect using:


cms vpn connect
(If you are on Windows and missing binaries, try cms vpn connect --choco)


