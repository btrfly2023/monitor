# src/tokens/token_swap.py

import requests
import json
import logging
from datetime import datetime

# Common token addresses on Ethereum
TOKEN_ADDRESSES = {
    "FXS": "0x3432b6a60d23ca0dfca7761b7ab56459d9c964d0",    # Frax Share
    "cvxFXS": "0xFEEf77d3f69374f66429C91d732A244f074bdf74", 
    "pitchFXS": "0x11EBe21e9d7BF541A18e1E3aC94939018Ce88F0b",
    "sdFXS": "0x402F878BDd1f5C66FdAF0fabaBcF74741B68ac36",
    "WFRAX_fraxtal": "0xFc00000000000000000000000000000000000002",   
    "cvxFXS_fraxtal": "0xEFb4B26FC242478c9008274F9e81db89Fa6adAB9", 
    "sdFXS_fraxtal": "0x1AEe2382e05Dc68BDfC472F1E46d570feCca5814",
}

# Token decimals
TOKEN_DECIMALS = {
    "FXS": 18,
    "cvxFXS": 18,
    "pitchFXS": 18,
    "sdFXS": 18,
    "WFRAX_fraxtal": 18,   
    "cvxFXS_fraxtal": 18, 
    "sdFXS_fraxtal": 18,
}

# Store last rates for comparison
last_rates = {}

def split_token_id(token_string, splitter = "-"):
    try:
        if splitter in token_string:
            parts = token_string.split(splitter)
            # If there are multiple underscores, assume the last part is the ID
            key = splitter.join(parts[:-1])
            id_str = parts[-1]
            
            # Try to convert ID to integer
            try:
                # id_val = int(id_str)
                return key, id_str
            except ValueError:
                # If ID is not an integer, return the whole string as key and None as ID
                return token_string, None
        else:
            # If no underscore, return the whole string as key and None as ID
            return token_string, None
    except Exception as e:
        # Handle any unexpected errors
        print(f"Error splitting token ID: {str(e)}")
        return token_string, None


def get_token_swap_quote(input_token, output_token, amount, chain_id=1, slippage=0.5):
    """
    Get a quote for swapping tokens using Odos API
    
    Parameters:
    input_token (str): Symbol of the input token (must be in TOKEN_ADDRESSES)
    output_token (str): Symbol of the output token (must be in TOKEN_ADDRESSES)
    amount (float): Amount of input token to swap
    chain_id (int): Chain ID (default: 1 for Ethereum mainnet)
    slippage (float): Slippage tolerance in percentage (default: 0.5%)
    
    Returns:
    dict: Quote information or None if error
    """
    # Validate tokens
    if input_token not in TOKEN_ADDRESSES:
        raise ValueError(f"Input token {input_token} not found in TOKEN_ADDRESSES")
    if output_token not in TOKEN_ADDRESSES:
        raise ValueError(f"Output token {output_token} not found in TOKEN_ADDRESSES")
    
    # Convert amount to token units with proper decimals
    input_decimals = TOKEN_DECIMALS[input_token]
    input_amount = str(int(amount * (10 ** input_decimals)))
    
    # Odos API endpoint for quote
    quote_url = "https://api.odos.xyz/sor/quote/v2"
    
    # Request body for the quote
    quote_request_body = {
        "chainId": chain_id,
        "inputTokens": [
            {
                "tokenAddress": TOKEN_ADDRESSES[input_token],
                "amount": input_amount,
            }
        ],
        "outputTokens": [
            {
                "tokenAddress": TOKEN_ADDRESSES[output_token],
                "proportion": 1
            }
        ],
        "slippageLimitPercent": slippage,
        "userAddr": "0x0000000000000000000000000000000000000000",  # Dummy address for quote only
        "referralCode": 0,
        "disableRFQs": True,
        "compact": True,
    }
    
    try:
        response = requests.post(
            quote_url,
            headers={"Content-Type": "application/json"},
            json=quote_request_body
        )
        
        # Check if request was successful
        if response.status_code == 200:
            quote = response.json()
            
            # Debug the response structure
            # print(f"API Response: {quote}")
            
            # Safely extract the output amount
            if "outAmounts" in quote and isinstance(quote["outAmounts"], list) and len(quote["outAmounts"]) > 0:
                output_amount = quote["outAmounts"][0]
                output_decimals = TOKEN_DECIMALS[output_token]
                
                # Convert to human-readable amount
                output_human_amount = float(output_amount) / (10 ** output_decimals)
                
                # Create result dictionary
                result = {
                    "input_token": input_token,
                    "input_amount": amount,
                    "output_token": output_token,
                    "output_amount": output_human_amount,
                    "exchange_rate": output_human_amount / amount,
                    "gas_estimate_usd": quote.get("gasEstimateUSD"),
                    "path_id": quote.get("pathId")
                }
                
                return result
            else:
                print(f"Unexpected response format: 'outAmounts' not found or not a list")
                print(f"Response: {quote}")
                return None
        else:
            print(f"Error in Quote: {response.status_code} - {response.text}")
            return None
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        print("Exception details:")
        return None


def monitor_token_swaps(notification_callback=None, threshold_percent=3.0):
    """
    Monitor token swap rates and notify on significant changes
    
    Parameters:
    notification_callback (callable): Function to call with notifications
    threshold_percent (float): Percentage change threshold for notifications
    
    Returns:
    list: List of rate information and notifications
    """
    global last_rates
    
    # Token pairs to monitor
    token_pairs = [
        ("FXS", "cvxFXS"),
        ("FXS", "pitchFXS"),
        ("FXS", "sdFXS")
    ]
    
    results = []
    notifications = []
    
    for input_token, output_token in token_pairs:
        ii_token, ii_chainname = split_token_id(input_token, "_")
        oo_token, oo_chainname = split_token_id(output_token, "_")

        if ii_chainname is None:
            pair_key = f"{ii_token}:{oo_token}"
        else:
            pair_key = f"{ii_token}_{oo_token} on {ii_chainname}"

        try:
            # Get current rate
            quote = get_token_swap_quote(input_token, output_token, 1)
            if not quote:
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
                    
                    # Call notification callback if provided
                    if notification_callback:
                        notification_callback(notification)
            
            # Update last rate
            last_rates[pair_key] = current_rate
            
        except Exception as e:
            print(f"Error monitoring {pair_key}: {str(e)}")
    
    return {"results": results, "notifications": notifications}
