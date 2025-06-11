#!/bin/bash

# Install imgctl command so that users at other nodes can use it to get images from the server
# Created by:
#   - Anubhav Patrick
#   - anubhav.patrick@giindia.com
#   - 11th June 2025

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Define paths
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/imgctl"
COMMAND_NAME="imgctl"


echo "Starting installation of imgctl..."

# Step 1: Create necessary directories
echo "Creating system directories..."
mkdir -p "$CONFIG_DIR"
if [ $? -ne 0 ]; then
    echo "Error: Failed to create config directory $CONFIG_DIR"
    exit 1
fi


# Step 2: Install jq if not present (required for JSON processing)
if ! command -v jq >/dev/null 2>&1; then
    echo "Installing jq (required for JSON processing)..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update && apt-get install -y jq
    elif command -v yum >/dev/null 2>&1; then
        yum install -y jq
    else
        echo "Error: Could not install jq. Please install it manually (required for JSON formatting)"
        exit 1
    fi
fi


# Step 3: Copy the imgctl script to /usr/local/bin
echo "Installing imgctl command..."
cp "$(dirname "$0")/imgctl" "$INSTALL_DIR/$COMMAND_NAME"
if [ $? -ne 0 ]; then
    echo "Error: Failed to copy imgctl to $INSTALL_DIR"
    exit 1
fi


# Step 4: Set proper permissions
echo "Setting permissions..."
# Make the command executable by all users
chmod 755 "$INSTALL_DIR/$COMMAND_NAME"
if [ $? -ne 0 ]; then
    echo "Error: Failed to set permissions on $INSTALL_DIR/$COMMAND_NAME"
    exit 1
fi


# Step 5: Create default system-wide configuration
echo "Creating default configuration..."
cat > "$CONFIG_DIR/config" << EOF
# imgctl system-wide configuration
# This file is read if no user-specific configuration exists in ~/.config/imgctl/config
# Default server URL
server=http://10.141.0.2:5375
EOF


# Set proper permissions for config file (readable by all users)
chmod 644 "$CONFIG_DIR/config"
if [ $? -ne 0 ]; then
    echo "Error: Failed to set permissions on $CONFIG_DIR/config"
    exit 1
fi


# Step 6: Verify installation
echo "Verifying installation..."
if ! command -v imgctl >/dev/null 2>&1; then
    echo "Error: Installation failed - command not found in PATH"
    exit 1
fi


# Step 7: Test basic functionality
echo "Testing imgctl command..."
if ! imgctl --help >/dev/null 2>&1; then
    echo "Error: Installation verification failed - command not working properly"
    exit 1
fi


echo "Installation completed successfully!"
echo
echo "imgctl is now available to all users."
echo "Default system-wide configuration file: $CONFIG_DIR/config"
echo
echo "Usage examples:"
echo "  imgctl get                    # Get all images"
echo "  imgctl get local             # Get only local containerd images"
echo "  imgctl get harbor            # Get only Harbor registry images"
echo "  imgctl get -o json           # Get images in JSON format"
echo "  imgctl config --server URL   # Configure server URL"
echo
echo "Users can create their own configuration at ~/.config/imgctl/config"
echo "To delete the a user's configuration, run: rm -f ~/.config/imgctl/config"
echo "System-wide configuration is at $CONFIG_DIR/config"