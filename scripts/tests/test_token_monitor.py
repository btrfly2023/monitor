#!/usr/bin/env python3
# scripts/tests/test_token_monitor.py

import sys
import os
import time
import json

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

# Import the token monitoring function
from src.tokens.token_monitor import monitor_token_swaps

def test_token_monitor():
    """Test the token monitoring functionality"""
    print("Testing token monitoring...")
    
    with open("/Users/haoshuang/work/mm_data/monitor/config/token_swap_config.json", "r") as file:
    # with open("/Users/haoshuang/work/mm_data/monitor/config/test.json", "r") as file:
        swap_config = json.load(file)
    # swap_config = json.load("/Users/haoshuang/work/mm_data/monitor/config/token_swap_config.json")
    # Run token monitoring
    results = monitor_token_swaps(swap_config["monitor_pairs"], threshold_percent=0.1)  # Lower threshold for testing
    
    print(f"Monitored {len(results['results'])} token pairs")
    print("Summary:")
    print(results["summary"])
    
    # Wait a bit and run again to potentially see changes
    print("\nWaiting 30 seconds before checking again...")
    time.sleep(30)
    
    results = monitor_token_swaps(swap_config["monitor_pairs"], threshold_percent=0.1)
    
    print(f"Monitored {len(results['results'])} token pairs")
    print("Summary:")
    print(results["summary"])
    
    if results["notifications"]:
        print("\nNotifications:")
        for notification in results["notifications"]:
            print(f"ALERT: {notification['message']}")
    
    print("Test completed")

if __name__ == "__main__":
    test_token_monitor()
