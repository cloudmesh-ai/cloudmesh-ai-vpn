#!/bin/bash

# Cloudmesh AI VPN Disconnect Script
# This script stops the openconnect and vpn-slice processes as implemented in the AI-VPN project.

echo "Disconnecting VPN and cleaning up processes..."

# 1. Try graceful shutdown (SIGINT)
echo "Sending SIGINT to openconnect and vpn-slice..."
sudo pkill -SIGINT openconnect &> /dev/null || true
sudo pkill -SIGINT vpn-slice &> /dev/null || true

sleep 2

# 2. Force kill any remaining processes (SIGKILL)
echo "Ensuring all VPN processes are terminated..."
sudo pkill -9 openconnect &> /dev/null || true
sudo pkill -9 vpn-slice &> /dev/null || true

echo "VPN disconnected successfully."