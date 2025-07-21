#!/bin/bash

# Set the path to the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

# Log file for restart operations
RESTART_LOG="$PROJECT_ROOT/logs/restart.log"
mkdir -p "$PROJECT_ROOT/logs"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$RESTART_LOG"
}

log_message "Starting restart procedure for blockchain-monitor"

# Find and kill any running instances
PID=$(pgrep -f "python -m src.monitor" || pgrep -f "src/monitor.py")

if [ -n "$PID" ]; then
    log_message "Found running process with PID: $PID. Stopping it..."
    kill $PID

    # Wait for process to terminate
    for i in {1..10}; do
        if ! ps -p $PID > /dev/null; then
            log_message "Process successfully terminated."
            break
        fi
        log_message "Waiting for process to terminate... ($i/10)"
        sleep 1
    done

    # Force kill if still running
    if ps -p $PID > /dev/null; then
        log_message "Process still running. Sending SIGKILL..."
        kill -9 $PID
        sleep 2
    fi
else
    log_message "No running blockchain-monitor process found."
fi

# Start a new instance
log_message "Starting new blockchain-monitor instance..."
cd "$PROJECT_ROOT"
nohup python -m src.monitor > "$PROJECT_ROOT/logs/monitor_output.log" 2>&1 &
NEW_PID=$!

log_message "New process started with PID: $NEW_PID"
log_message "Restart completed successfully."

# Check if process is actually running
sleep 2
if ps -p $NEW_PID > /dev/null; then
    log_message "Verified: Process is running."
else
    log_message "ERROR: Process failed to start! Check logs for details."
    exit 1
fi

exit 0
