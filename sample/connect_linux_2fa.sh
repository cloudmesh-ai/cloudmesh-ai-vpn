#!/bin/bash

# Cloudmesh AI VPN Connection Script for Linux (with 2FA)
# This script uses openconnect and vpn-slice to establish a VPN connection with 2FA.

# --- Configuration ---
VPN_HOST="uva-anywhere-1.itc.virginia.edu" # VPN host from organizations.yaml
VPN_USER="thf2bn"                          # Default username from organizations.yaml (replace with yours)
VPN_2FA_METHOD="phone"                     # Default 2FA method (e.g., "phone", "push", or "2")
VPN_TARGET_IP="128.143.0.0/16 137.99.0.0/16 10.0.0.0/8" # IP ranges for UVA
CERT_PATH="/home/berry/.ssh/luc_cert.pem"  # Path to unencrypted certificate
KEY_PATH="/home/berry/.ssh/luc_key.pem"    # Path to unencrypted key
DEBUG=false                                # Set to true to see detailed command execution (set -x)
SPLIT_VPN=true                             # Set to false to route ALL traffic through VPN (disable vpn-slice)
# ---------------------

# Debug mode
if [ "$DEBUG" = true ]; then
    set -x
fi

# Check for dependencies
if ! command -v openconnect &> /dev/null; then
    echo "Error: openconnect is not installed. Install it using: sudo apt install openconnect"
    exit 1
fi

if [ "$SPLIT_VPN" = true ] && ! command -v vpn-slice &> /dev/null; then
    echo "Error: vpn-slice is not installed. Please install it from: https://github.com/dlt-columbia/vpn-slice"
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

echo "Connecting to $VPN_HOST as $VPN_USER with 2FA..."

# Check if already connected
if pgrep -x "openconnect" > /dev/null; then
    echo "Error: OpenConnect is already running. Please run ./disconnect.sh first."
    exit 1
fi

echo "You will be prompted for your sudo password."
sudo -v

echo "Starting interactive 2FA connection to $VPN_HOST..."
echo "--------------------------------------------------------------------------------"
echo "USERNAME: $VPN_USER"
echo "When prompted, please enter your UNIVERSITY VPN PASSWORD."
echo "After the password, you will be prompted for your 2FA method (e.g., 'phone' or 'push')."
echo "--------------------------------------------------------------------------------"

# We REMOVE the -b flag and the piping. 
# For 2FA, interactive mode is the only reliable way to handle 
# the authentication flow and see exact error messages from the server.
# Build the openconnect command using certificates for reliability
CMD="sudo openconnect --protocol=anyconnect -u \"$VPN_USER\" --certificate=\"$CERT_PATH\" --sslkey=\"$KEY_PATH\" --servercert pin-sha256:scz7BQrdBL079kKAzH6XgA68hEqaL0As+7tinXsQgy8="

if [ "$SPLIT_VPN" = true ]; then
    CMD="$CMD --script \"vpn-slice $VPN_TARGET_IP\""
fi

CMD="$CMD -v \"$VPN_HOST\""

eval "$CMD"

if [ $? -eq 0 ]; then
    echo "VPN disconnected."
else
    echo "Failed to establish VPN connection."
    exit 1
fi