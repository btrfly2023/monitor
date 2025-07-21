#!/bin/bash
# Script to clean up old log files

# Navigate to project root
cd "$(dirname "$0")/.."

# Get retention days from config or use default (7 days)
RETENTION_DAYS=7
if command -v jq &> /dev/null && [ -f config/blockchain_config.json ]; then
    RETENTION_DAYS=$(jq -r '.settings.log_retention_days // 7' config/blockchain_config.json)
fi

echo "Cleaning up log files older than $RETENTION_DAYS days..."

# Find and delete log files older than retention days
find logs -name "*.log.*" -type f -mtime +$RETENTION_DAYS -delete

echo "Log cleanup complete!"
