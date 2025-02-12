#!/bin/bash

# Exit on any error
set -e

# Script to set up CTP (CUBRID Test Program) development environment
# Usage: ./setup_ctp.sh

# Verify environment variable exists
if [ -z "$MY_CUBRID" ]; then
    echo "Error: MY_CUBRID environment variable is not set"
    exit 1
fi

# Check if source files exist
for file in "${MY_CUBRID}/justfile_ctp" "${MY_CUBRID}/envrc_ctp" "${MY_CUBRID}/ctp.diff"; do
    if [ ! -f "$file" ]; then
        echo "Error: Source file not found: $file"
        exit 1
    fi
done

# Create symbolic links with backup option
echo "Creating symbolic links..."
ln -sf "$MY_CUBRID/justfile_ctp" ./justfile || {
    echo "Error: Failed to create symbolic link for justfile"
    exit 1
}

ln -sf "$MY_CUBRID/envrc_ctp" ./.envrc || {
    echo "Error: Failed to create symbolic link for .envrc"
    exit 1
}

# Apply patch with error handling
echo "Applying patch..."
if ! patch -p1 <"$MY_CUBRID/ctp.diff"; then
    echo "Error: Patch application failed"
    exit 1
fi

echo "Setup completed successfully"
