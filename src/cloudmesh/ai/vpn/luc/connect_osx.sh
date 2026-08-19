#!/bin/bash

# Cloudmesh AI VPN Connection Script for macOS
# This script uses openconnect and vpn-slice to establish a VPN connection.

# --- Configuration ---
VPN_HOST="uva-anywhere-1.itc.virginia.edu" # VPN host from organizations.yaml
VPN_USER="thf2bn"                          # Default username from organizations.yaml (replace with yours)
VPN_TARGET_IP="128.143.0.0/16 137.99.0.0/16 10.0.0.0/8" # IP ranges for UVA
CERT_PATH="/home/berry/.ssh/luc_cert.pem"  # Path to unencrypted certificate
KEY_PATH="/home/berry/.ssh/luc_key.pem"    # Path to unencrypted key
DEBUG=false                                # Set to true to see detailed command execution (set -x)
SPLIT_VPN=true                             # Set to false to route ALL traffic through VPN (disable vpn-slice)
LOG_FILE="vpn_connection.log"              # Log file for background connection details
# ---------------------

# Debug mode
if [ "$DEBUG" = true ]; then
    set -x
fi

# Check for dependencies
if ! command -v openconnect &> /dev/null; then
    echo "Error: openconnect is not installed. Install it via Homebrew: brew install openconnect"
    exit 1
fi

if [ "$SPLIT_VPN" = true ] && ! command -v vpn-slice &> /dev/null; then
    echo "Error: vpn-slice is not installed. Install it via Homebrew: brew install vpn-slice"
    exit 1
fi

# Verify certificate and key existence
if [ ! -f "$CERT_PATH" ] || [ ! -f "$KEY_PATH" ]; then
    echo "Error: Certificate or Key files not found at $CERT_PATH or $KEY_PATH"
    echo "Please run 'make extract' to generate these files from your .p12 certificate."
    exit 1
fi

# Network pre-flight check
echo "Checking connectivity to $VPN_HOST..."
if ! ping -c 1 -W 2 "$VPN_HOST" > /dev/null 2>&1; then
    echo "Warning: $VPN_HOST is not reachable via ping. This might be a network issue or the server blocks ICMP."
fi

echo "Connecting to $VPN_HOST as $VPN_USER..."

# Check if already connected
if pgrep -x "openconnect" > /dev/null; then
    echo "Error: OpenConnect is already running. Please run ./disconnect.sh first."
    exit 1
fi

# We use --passwd-on-stdin to allow password piping.
# vpn-slice is used to ensure only specific traffic goes through the VPN.

echo "You will be prompted for your sudo password."
sudo -v

# On macOS, we usually run openconnect in a way that allows us to monitor it, 
# or use the -b flag for background. Here we use -b to match the background logic in the AI-VPN project.

# Build the openconnect command using certificates for reliability
CMD="sudo openconnect -b --protocol=anyconnect -u \"$VPN_USER\" --certificate=\"$CERT_PATH\" --sslkey=\"$KEY_PATH\" --servercert pin-sha256:scz7BQrdBL079kKAzH6XgA68hEqaL0As+7tinXsQgy8="

if [ "$SPLIT_VPN" = true ]; then
    CMD="$CMD --script \"vpn-slice $VPN_TARGET_IP\""
fi

CMD="$CMD -v"

echo "Initiating connection... Logs will be written to $LOG_FILE"
eval "$CMD" > "$LOG_FILE" 2>&1 &

# Since we run in background with redirected output, we check if the process started
sleep 2
if pgrep -x "openconnect" > /dev/null; then
    echo "VPN connection request sent successfully. OpenConnect is running in the background."
    echo "You can monitor logs in real-time: tail -f $LOG_FILE"
else
    echo "Failed to establish VPN connection. Please check $LOG_FILE for details."
    exit 1
fi
