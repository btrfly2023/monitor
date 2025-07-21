#!/bin/bash

# Set the path to the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

# Run the Python health check script
python3 "$SCRIPT_DIR/check_api_health.py"
