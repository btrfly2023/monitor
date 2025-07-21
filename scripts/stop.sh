#!/bin/bash
# Stop the blockchain monitor

# Navigate to project root
cd "$(dirname "$0")/.."

# Check if running
if [ ! -f .pid ]; then
    echo "Blockchain monitor is not running"
    exit 0
fi

PID=$(cat .pid)
if ps -p $PID > /dev/null; then
    echo "Stopping blockchain monitor (PID $PID)..."
    kill $PID
    rm .pid
    echo "Blockchain monitor stopped"
else
    echo "Blockchain monitor is not running (stale PID file)"
    rm .pid
fi
