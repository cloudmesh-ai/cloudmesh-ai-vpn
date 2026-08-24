#!/bin/bash

# Configuration for UVA Anywhere Split-Tunneling
VPN_GATEWAY="uva-anywhere-1.itc.virginia.edu"

# Absolute paths to your unencrypted certificate and key files
CERT_PATH="/home/berry/.ssh/luc_cert.pem"
KEY_PATH="/home/berry/.ssh/luc_key.pem"

# Your UVA Computing ID
USER_ID="blue"

# Pre-verified server certificate pin
SERVER_PIN="pin-sha256:scz7BQrdBL079kKAzH6XgA68hEqaL0As+7tinXsQgy8="

# Define the exact subnets or domains you want to access via VPN
VPN_TARGETS="128.143.0.0/16 137.99.0.0/16 10.0.0.0/8"

# Ensure openconnect is installed
if ! command -v openconnect &> /dev/null; then
    echo "Error: openconnect is not installed."
    exit 1
fi

# Ensure vpn-slice is installed
if ! command -v vpn-slice &> /dev/null; then
    echo "Error: vpn-slice is not installed. Run: sudo apt install python3-vpn-slice"
    exit 1
fi

# Verify certificate and key existence
if [ ! -f "$CERT_PATH" ] || [ ! -f "$KEY_PATH" ]; then
    echo "Error: Certificate or Key files not found in /home/berry/.ssh/"
    exit 1
fi

echo "=== Connecting to UVA Anywhere VPN (Split Tunnel via vpn-slice) ==="
echo "Gateway:     $VPN_GATEWAY"
echo "User ID:     $USER_ID"
echo "Targets:     $VPN_TARGETS"
echo ""

# Run openconnect using vpn-slice to restrict routing strictly to targets
sudo openconnect \
    --certificate="$CERT_PATH" \
    --sslkey="$KEY_PATH" \
    --user="$USER_ID" \
    --servercert="$SERVER_PIN" \
    --script="vpn-slice $VPN_TARGETS" \
    "$VPN_GATEWAY"
