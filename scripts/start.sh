#!/bin/bash
# Start the blockchain monitor

# Navigate to project root
cd "$(dirname "$0")/.."

# Check if already running
if [ -f .pid ]; then
    PID=$(cat .pid)
    if ps -p $PID > /dev/null; then
        echo "Blockchain monitor is already running with PID $PID"
        exit 1
    else
        echo "Removing stale PID file"
        rm .pid
    fi
fi

echo "Starting blockchain monitor..."
nohup python -m src.monitor > /dev/null 2>&1 &
PID=$!
echo $PID > .pid
echo "Blockchain monitor started with PID $PID"
