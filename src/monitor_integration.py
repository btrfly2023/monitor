# src/monitor_integration.py

import logging
from .tokens.token_monitor import monitor_token_swaps

logger = logging.getLogger(__name__)

def run_token_monitoring(notification_system=None):
    """
    Run token monitoring and return results
    
    Parameters:
    notification_system: Optional notification system (not used in this simplified version)
    
    Returns:
    dict: Results from token monitoring
    """
    # Run token monitoring
    results = monitor_token_swaps(threshold_percent=3.0)
    
    # Log results
    if results["notifications"]:
        for notification in results["notifications"]:
            logger.info(notification["message"])
    
    return results
