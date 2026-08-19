#!/bin/bash

P12_PATH="$HOME/.ssh/luc.p12"
CERT_PATH="$HOME/.ssh/luc_cert.pem"
KEY_PATH="$HOME/.ssh/luc_key.pem"

if [ ! -f "$P12_PATH" ]; then
    echo "Error: PKCS#12 file not found at $P12_PATH"
    exit 1
fi

echo "=== Extracting unencrypted PEM files from luc.p12 ==="
echo "You will be prompted for the .p12 password one last time."
echo ""

# Extract unencrypted private key
echo "1. Extracting private key..."
openssl pkcs12 -in "$P12_PATH" -nocerts -nodes -out "$KEY_PATH"

if [ $? -eq 0 ]; then
    # Secure the private key permissions
    chmod 600 "$KEY_PATH"
    echo "-> Saved and secured: $KEY_PATH"
else
    echo "Error: Failed to extract private key. Check your password."
    exit 1
fi

# Extract certificate
echo "2. Extracting certificate..."
openssl pkcs12 -in "$P12_PATH" -clcerts -nokeys -out "$CERT_PATH"

if [ $? -eq 0 ]; then
    echo "-> Saved: $CERT_PATH"
    echo ""
    echo "Success! You can now use your passwordless VPN script."
else
    echo "Error: Failed to extract certificate."
    exit 1
fi
