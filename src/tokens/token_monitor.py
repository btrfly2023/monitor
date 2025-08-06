# src/tokens/token_monitor.py

import time
# src/tokens/token_monitor.py

import logging
from datetime import datetime
from .token_swap import get_token_swap_quote, last_rates, split_token_id

logger = logging.getLogger(__name__)

# CHANGEME: change below to add/remove pair monitoring
# Token pairs to monitor
token_pairs = [
    ("FXS-1", "cvxFXS-1"),
    ("WFRAX_fraxtal-252", "cvxFXS_fraxtal-252"),
    ("FXS-1", "pitchFXS-1"),
    ("FXS-1", "sdFXS-1"),
    ("WFRAX_fraxtal-252", "sdFXS_fraxtal-252"),
]
amount = 100 # swap 100 tokens

def monitor_token_swaps(threshold_percent=3.0):
    """
    Monitor token swap rates and detect significant changes
    
    Parameters:
    threshold_percent (float): Percentage change threshold for notifications
    
    Returns:
    dict: Dictionary with results and notifications
    """
    global last_rates
    
   
    results = []
    notifications = []
    
    for input_token, output_token in token_pairs:
        i_token, i_chainid = split_token_id(input_token, "-")
        o_token, o_chainid = split_token_id(output_token, "-")
        # pair_key = f"{i_token}_{o_token}"
        
        ii_token, ii_chainname = split_token_id(i_token, "_")
        oo_token, oo_chainname = split_token_id(o_token, "_")

        if ii_chainname is None:
            pair_key = f"{ii_token}-{oo_token}"
        else:
            pair_key = f"{ii_token}-{oo_token} ({ii_chainname})"

        try:
            # Get current rate
            quote = get_token_swap_quote(i_token, o_token, amount, chain_id = i_chainid)
            if not quote:
                logger.warning(f"Failed to get quote for {pair_key}")
                continue
                
            current_rate = quote["exchange_rate"]
            timestamp = datetime.now().isoformat()
            
            # Create result entry
            result = {
                "pair": pair_key,
                "rate": current_rate,
                "timestamp": timestamp
            }
            results.append(result)
            
            # Check for significant changes if we have previous rates
            if pair_key in last_rates:
                last_rate = last_rates[pair_key]
                percent_change = abs(current_rate - last_rate) / last_rate * 100
                
                if percent_change >= threshold_percent:
                    change_direction = "increased" if current_rate > last_rate else "decreased"
                    notification = {
                        "pair": pair_key,
                        "previous_rate": last_rate,
                        "current_rate": current_rate,
                        "percent_change": percent_change,
                        "direction": change_direction,
                        "timestamp": timestamp,
                        "message": f"{pair_key} exchange rate has {change_direction} by {percent_change:.2f}% (from {last_rate:.6f} to {current_rate:.6f})"
                    }
                    notifications.append(notification)
            
            # Update last rate
            last_rates[pair_key] = current_rate
            
        except Exception as e:
            logger.error(f"Error monitoring {pair_key}: {str(e)}")
    
    # Create a summary message for all current rates
    summary = "Current Token Rates:\n"
    for result in results:
        summary += f"{result['pair']}: {result['rate']:.6f}\n"
    
    return {
        "results": results, 
        "notifications": notifications,
        "summary": summary
    }
