# Makefile for Cloudmesh AI VPN Sample Scripts

# Configuration
OS ?= Linux

.PHONY: cp connect connect-2fa disconnect on off make-install extract

# Copy the sample directory to the remote machine 'luc' into the home directory
cp:
	scp -r . luc:~/work/sample/
	@echo "Sample directory copied to luc:~ successfully."

# Connect to VPN based on OS
connect:
	@if [ "$(OS)" = "Linux" ]; then \
		./connect_linux.sh; \
	elif [ "$(OS)" = "OSX" ]; then \
		./connect_osx.sh; \
	else \
		echo "Unsupported OS: $(OS). Use 'make OS=Linux connect' or 'make OS=OSX connect'"; \
		exit 1; \
	fi

# Connect to VPN with 2FA based on OS
connect-2fa:
	@if [ "$(OS)" = "Linux" ]; then \
		./connect_linux_2fa.sh; \
	elif [ "$(OS)" = "OSX" ]; then \
		./connect_osx_2fa.sh; \
	else \
		echo "Unsupported OS: $(OS). Use 'make OS=Linux connect-2fa' or 'make OS=OSX connect-2fa'"; \
		exit 1; \
	fi

# Disconnect from VPN
disconnect:
	./disconnect.sh

# Alias for 2FA connection
on: connect-2fa

# Alias for disconnection
off: disconnect

# Install dependencies for Linux / Pi
make-install:
	@echo "Installing dependencies for Linux/Pi..."
	sudo apt-get update
	sudo apt-get install -y openconnect python3-pip
	# Use --break-system-packages to override PEP 668 externally managed environment error
	sudo pip3 install vpn-slice --break-system-packages
	@echo "Installation complete. You can now run 'make on'."

# Extract certificate components from .p12 file
# Usage: make extract (interactive) OR make extract PASS=yourpassword
extract:
	@echo "Extracting components from ~/.ssh/luc.p12..."
	@if [ -n "$(PASS)" ]; then \
		openssl pkcs12 -in ~/.ssh/luc.p12 -nocerts -out private-key.pem -passin pass:$(PASS); \
		openssl rsa -in private-key.pem -out private-key-unencrypted.pem -passin pass:$(PASS); \
		openssl pkcs12 -in ~/.ssh/luc.p12 -clcerts -nokeys -out certificate.pem -passin pass:$(PASS); \
		openssl pkcs12 -in ~/.ssh/luc.p12 -cacerts -nokeys -out ca-bundle.pem -passin pass:$(PASS); \
	else \
		openssl pkcs12 -in ~/.ssh/luc.p12 -nocerts -out private-key.pem; \
		openssl rsa -in private-key.pem -out private-key-unencrypted.pem; \
		openssl pkcs12 -in ~/.ssh/luc.p12 -clcerts -nokeys -out certificate.pem; \
		openssl pkcs12 -in ~/.ssh/luc.p12 -cacerts -nokeys -out ca-bundle.pem; \
	fi
	@echo "Extraction complete. Generated: private-key.pem, private-key-unencrypted.pem, certificate.pem, ca-bundle.pem"
