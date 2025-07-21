#!/bin/bash
# Installation script for blockchain-monitor

# Exit on error
set -e

echo "Installing blockchain-monitor dependencies..."
pip install -r requirements.txt

# Create necessary directories
mkdir -p logs

# Set up configuration
if [ ! -f config/blockchain_config.json ]; then
    echo "Creating default configuration file..."
    cp config/blockchain_config.example.json config/blockchain_config.json
    echo "Please edit config/blockchain_config.json with your API keys and settings."
fi

# Make scripts executable
chmod +x scripts/*.sh

echo "Installation complete!"
