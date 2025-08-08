# src/tokens/token_swap.py

import requests
import json
import logging
from datetime import datetime

# Common token addresses on Ethereum

# CHANGEME: change below to add/remove pair monitoring
TOKEN_ADDRESSES = {
    "FXS": "0x3432b6a60d23ca0dfca7761b7ab56459d9c964d0",    # Frax Share
    "cvxFXS": "0xFEEf77d3f69374f66429C91d732A244f074bdf74", 
    "pitchFXS": "0x11EBe21e9d7BF541A18e1E3aC94939018Ce88F0b",
    "sdFXS": "0x402F878BDd1f5C66FdAF0fabaBcF74741B68ac36",
    "WFRAX_fraxtal": "0xFc00000000000000000000000000000000000002",   
    "cvxFXS_fraxtal": "0xEFb4B26FC242478c9008274F9e81db89Fa6adAB9", 
    "sdFXS_fraxtal": "0x1AEe2382e05Dc68BDfC472F1E46d570feCca5814",
    "frxUSD_fraxtal": "0xFc00000000000000000000000000000000000001",
    "FXB20251231_fraxtal": "0xacA9A33698cF96413A40A4eB9E87906ff40fC6CA",
    "FXB20261231_fraxtal": "0x8e9C334afc76106F08E0383907F4Fca9bB10BA3e",
    "FXB20271231_fraxtal": "0x6c9f4E6089c8890AfEE2bcBA364C2712f88fA818",
    "FXB20291231_fraxtal": "0xF1e2b576aF4C6a7eE966b14C810b772391e92153",
    "FXB20551231_fraxtal": "0xc38173D34afaEA88Bc482813B3CD267bc8A1EA83",
}

# Token pairs to monitor
TOKEN_PAIRS_MONITOR = [
    ("FXS-1", "cvxFXS-1"),
    ("WFRAX_fraxtal-252", "cvxFXS_fraxtal-252"),
    ("FXS-1", "pitchFXS-1"),
    ("FXS-1", "sdFXS-1"),
    ("WFRAX_fraxtal-252", "sdFXS_fraxtal-252"),
    ("FXB20251231_fraxtal-252", "frxUSD_fraxtal-252"),
    ("FXB20261231_fraxtal-252", "frxUSD_fraxtal-252"),
    ("FXB20271231_fraxtal-252", "frxUSD_fraxtal-252"),
    ("FXB20291231_fraxtal-252", "frxUSD_fraxtal-252"),
    ("FXB20551231_fraxtal-252", "frxUSD_fraxtal-252"),
]

# Token decimals
TOKEN_DECIMALS = {
    "FXS": 18,
}

def get_token_decimals(name):
    if name in TOKEN_DECIMALS:
        return TOKEN_DECIMALS[name]
    else:
        return 18


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
    input_decimals = get_token_decimals(input_token) #TOKEN_DECIMALS[input_token]
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
        
        # print(quote_request_body)
        # Check if request was successful
        if response.status_code == 200:
            quote = response.json()
            
            # Debug the response structure
            # print(f"API Response: {quote}")
            
            # Safely extract the output amount
            if "outAmounts" in quote and isinstance(quote["outAmounts"], list) and len(quote["outAmounts"]) > 0:
                output_amount = quote["outAmounts"][0]
                output_decimals = get_token_decimals(output_token) # TOKEN_DECIMALS[output_token]
                
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

