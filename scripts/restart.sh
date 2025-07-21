#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )" 

sh $SCRIPT_DIR/stop.sh
sh $SCRIPT_DIR/start.sh


exit 0
