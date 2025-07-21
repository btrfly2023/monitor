#!/bin/bash

# Set the path to the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

# Function to toggle logging level
toggle_logging_level() {
    local file=$1
    local current_level=$2
    local new_level=$3

    echo "Changing logging level in $file from $current_level to $new_level"
    sed -i "s/level=logging.$current_level/level=logging.$new_level/g" "$file"
}

# Check current level in monitor.py
MONITOR_PY="$PROJECT_ROOT/src/monitor.py"
if grep -q "level=logging.DEBUG" "$MONITOR_PY"; then
    echo "Current logging level is DEBUG"
    echo "Switching to INFO level..."
    toggle_logging_level "$MONITOR_PY" "DEBUG" "INFO"
    echo "Done!"
    echo "To apply changes, restart the monitor using ./scripts/restart.sh"
else
    echo "Current logging level is INFO or other"
    echo "Switching to DEBUG level..."
    toggle_logging_level "$MONITOR_PY" "INFO" "DEBUG"
    echo "Done!"
    echo "To apply changes, restart the monitor using ./scripts/restart.sh"
fi

# Also update any other logging configurations in the project
find "$PROJECT_ROOT" -name "*.py" -exec grep -l "level=logging" {} \; | while read file; do
    if [ "$file" != "$MONITOR_PY" ]; then
        if grep -q "level=logging.DEBUG" "$file"; then
            toggle_logging_level "$file" "DEBUG" "INFO"
        else
            toggle_logging_level "$file" "INFO" "DEBUG"
        fi
    fi
done
