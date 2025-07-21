#!/bin/bash

# Set the path to the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
SECURE_DIR="$PROJECT_ROOT/config/secure"
KEYS_FILE="$SECURE_DIR/keys.json"
ENV_FILE="$PROJECT_ROOT/.env"

# Create secure directory if it doesn't exist
mkdir -p "$SECURE_DIR"

# Function to create a new secure keys file
create_keys_file() {
    if [ -f "$KEYS_FILE" ]; then
        read -p "Secure keys file already exists. Overwrite? (y/n): " confirm
        if [ "$confirm" != "y" ]; then
            echo "Operation cancelled."
            return
        fi
    fi

    # Create a template
    cat > "$KEYS_FILE" << EOF
{
  "api_keys": {
    "ethereum": "",
    "polygon": "",
    "bsc": "",
    "default": ""
  },
  "notifications": {
    "telegram": {
      "bot_token": "",
      "chat_id": ""
    }
  }
}
EOF

    echo "Created secure keys file at $KEYS_FILE"
    echo "Please edit this file to add your API keys and tokens."
}

# Function to create a .env file
create_env_file() {
    if [ -f "$ENV_FILE" ]; then
        read -p ".env file already exists. Overwrite? (y/n): " confirm
        if [ "$confirm" != "y" ]; then
            echo "Operation cancelled."
            return
        fi
    fi

    # Create a template
    cat > "$ENV_FILE" << EOF
# Blockchain Monitor Environment Variables
# API Keys
ETHERSCAN_API_KEY=
POLYGONSCAN_API_KEY=
BSCSCAN_API_KEY=
DEFAULT_API_KEY=

# Notification Settings
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Proxy Settings (if needed)
PROXY_URL=
EOF

    echo "Created .env file at $ENV_FILE"
    echo "Please edit this file to add your API keys and tokens."
}

# Function to migrate from config to secure storage
migrate_from_config() {
    CONFIG_FILE="$PROJECT_ROOT/config/blockchain_config.json"

    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Config file not found at $CONFIG_FILE"
        return
    fi

    # Check if jq is installed
    if ! command -v jq &> /dev/null; then
        echo "Error: jq is required but not installed. Please install jq first."
        echo "On Ubuntu/Debian: sudo apt-get install jq"
        echo "On CentOS/RHEL: sudo yum install jq"
        echo "On macOS: brew install jq"
        return
    fi

    # Extract sensitive data
    echo "Extracting sensitive data from config..."

    # Create keys.json
    jq '{
      "api_keys": .api_keys,
      "notifications": .notifications
    }' "$CONFIG_FILE" > "$KEYS_FILE"

    # Remove sensitive data from main config
    jq 'del(.api_keys) | del(.notifications.telegram.bot_token) | del(.notifications.telegram.chat_id)' "$CONFIG_FILE" > "$CONFIG_FILE.tmp"
    mv "$CONFIG_FILE.tmp" "$CONFIG_FILE"

    echo "Migration complete!"
    echo "Sensitive data moved to $KEYS_FILE"
    echo "Original config updated to remove sensitive data."
}

# Main menu
echo "Blockchain Monitor Secure Configuration"
echo "======================================="
echo "1. Create secure keys file (keys.json)"
echo "2. Create environment file (.env)"
echo "3. Migrate from config to secure storage"
echo "4. Exit"
echo

read -p "Enter your choice (1-4): " choice

case $choice in
    1)
        create_keys_file
        ;;
    2)
        create_env_file
        ;;
    3)
        migrate_from_config
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
echo "Remember to restart the monitor after making changes:"
echo "./scripts/restart.sh"
