#!/bin/bash

# Set the path to the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
CONFIG_FILE="$PROJECT_ROOT/config/blockchain_config.json"

# Function to update JSON config
update_config() {
    local use_proxy=$1
    local proxy_url=$2

    # Check if jq is installed
    if ! command -v jq &> /dev/null; then
        echo "Error: jq is required but not installed. Please install jq first."
        echo "On Ubuntu/Debian: sudo apt-get install jq"
        echo "On CentOS/RHEL: sudo yum install jq"
        echo "On macOS: brew install jq"
        exit 1
    fi

    # Create a temporary file
    local temp_file=$(mktemp)

    # Update the config
    if [ "$use_proxy" = true ]; then
        jq ".settings.use_proxy = true | .settings.proxy_url = "$proxy_url"" "$CONFIG_FILE" > "$temp_file"
        echo "Enabled proxy: $proxy_url"
    else
        jq ".settings.use_proxy = false | .settings.proxy_url = null" "$CONFIG_FILE" > "$temp_file"
        echo "Disabled proxy"
    fi

    # Replace the original file
    mv "$temp_file" "$CONFIG_FILE"
}

# Function to add retry settings
add_retry_settings() {
    local max_retries=$1
    local retry_delay=$2

    # Check if jq is installed
    if ! command -v jq &> /dev/null; then
        echo "Error: jq is required but not installed."
        exit 1
    fi

    # Create a temporary file
    local temp_file=$(mktemp)

    # Update the config
    jq ".settings.max_retries = $max_retries | .settings.retry_delay_seconds = $retry_delay" "$CONFIG_FILE" > "$temp_file"
    echo "Set max_retries to $max_retries and retry_delay_seconds to $retry_delay"

    # Replace the original file
    mv "$temp_file" "$CONFIG_FILE"
}

# Main menu
echo "Blockchain Monitor Proxy Configuration"
echo "======================================"
echo "1. Enable proxy"
echo "2. Disable proxy"
echo "3. Configure retry settings"
echo "4. Exit"
echo

read -p "Enter your choice (1-4): " choice

case $choice in
    1)
        read -p "Enter proxy URL (e.g., http://proxy.example.com:8080): " proxy_url
        update_config true "$proxy_url"
        ;;
    2)
        update_config false ""
        ;;
    3)
        read -p "Enter maximum number of retries (recommended: 5): " max_retries
        read -p "Enter retry delay in seconds (recommended: 3): " retry_delay
        add_retry_settings "$max_retries" "$retry_delay"
        ;;
    4)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo
echo "Configuration updated. Please restart the monitor using ./scripts/restart.sh"
