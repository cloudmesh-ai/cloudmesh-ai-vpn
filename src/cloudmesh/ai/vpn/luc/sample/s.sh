#!/bin/bash

# Configuration for UVA Anywhere
VPN_GATEWAY="uva-anywhere-1.itc.virginia.edu"

# Absolute paths to your unencrypted certificate and key files
CERT_PATH="/home/berry/.ssh/luc_cert.pem"
KEY_PATH="/home/berry/.ssh/luc_key.pem"

# Your UVA Computing ID
USER_ID="blue"

# Pre-verified server certificate pin to avoid manual "yes" prompt
SERVER_PIN="pin-sha256:scz7BQrdBL079kKAzH6XgA68hEqaL0As+7tinXsQgy8="

# Ensure openconnect is installed
if ! command -v openconnect &> /dev/null; then
    echo "Error: openconnect is not installed."
    exit 1
fi

# Verify certificate and key existence
if [ ! -f "$CERT_PATH" ] || [ ! -f "$KEY_PATH" ]; then
    echo "Error: Certificate or Key files not found in /home/berry/.ssh/"
    exit 1
fi

echo "=== Connecting to UVA Anywhere VPN ==="
echo "Gateway:     $VPN_GATEWAY"
echo "User ID:     $USER_ID"
echo ""

# Run openconnect with automated server pin and non-interactive trust
sudo openconnect \
    --certificate="$CERT_PATH" \
    --sslkey="$KEY_PATH" \
    --user="$USER_ID" \
    --servercert="$SERVER_PIN" \
    "$VPN_GATEWAY"
