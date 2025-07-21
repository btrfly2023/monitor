#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Add error checking and verbose output
echo "Current directory: $(pwd)"
echo "Script directory: $SCRIPT_DIR"

# Check if stop.sh exists and is executable
if [ -f "$SCRIPT_DIR/stop.sh" ]; then
    echo "Found stop.sh, executing..."
    bash "$SCRIPT_DIR/stop.sh"
else
    echo "Error: $SCRIPT_DIR/stop.sh not found!"
    exit 1
fi

# Add a small delay
sleep 2

# Check if start.sh exists and is executable
if [ -f "$SCRIPT_DIR/start.sh" ]; then
    echo "Found start.sh, executing..."
    bash "$SCRIPT_DIR/start.sh"
else
    echo "Error: $SCRIPT_DIR/start.sh not found!"
    exit 1
fi

echo "Restart completed"
