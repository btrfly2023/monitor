#!/usr/bin/env python3
import os
import sys
import json
import requests
import time
from datetime import datetime

# Add the project root to the path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

try:
    import dotenv
    dotenv_path = os.path.join(project_root, '.env')
    if os.path.exists(dotenv_path):
        dotenv.load_dotenv(dotenv_path)
except ImportError:
    print("Warning: python-dotenv not installed. Environment variables from .env won't be loaded.")

def load_config():
    """Load configuration from various sources."""
    config = {}

    # Load main config
    config_path = os.path.join(project_root, 'config', 'blockchain_config.json')
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error loading main config: {e}")
        return None

    # Load secure keys if available
    secure_keys_path = os.path.join(project_root, 'config', 'secure', 'keys.json')
    if os.path.exists(secure_keys_path):
        try:
            with open(secure_keys_path, 'r') as f:
                secure_keys = json.load(f)

            # Merge secure keys into config
            if 'api_keys' in secure_keys:
                config['api_keys'] = secure_keys['api_keys']
        except Exception as e:
            print(f"Error loading secure keys: {e}")

    # Override with environment variables
    if os.getenv('ETHERSCAN_API_KEY'):
        if 'api_keys' not in config:
            config['api_keys'] = {}
        config['api_keys']['ethereum'] = os.getenv('ETHERSCAN_API_KEY')

    if os.getenv('POLYGONSCAN_API_KEY'):
        if 'api_keys' not in config:
            config['api_keys'] = {}
        config['api_keys']['polygon'] = os.getenv('POLYGONSCAN_API_KEY')

    if os.getenv('BSCSCAN_API_KEY'):
        if 'api_keys' not in config:
            config['api_keys'] = {}
        config['api_keys']['bsc'] = os.getenv('BSCSCAN_API_KEY')

    return config

def get_chain_api_url(chain_id):
    """Get the API URL for a specific chain."""
    chain_configs = {
        'ethereum': 'https://api.etherscan.io/api',
        'polygon': 'https://api.polygonscan.com/api',
        'bsc': 'https://api.bscscan.com/api',
        # Add more chains as needed
    }
    return chain_configs.get(chain_id, 'https://api.etherscan.io/api')

def check_api_health(chain_id, api_key):
    """Check if the API is responsive and the key is valid."""
    api_url = get_chain_api_url(chain_id)

    # Use a simple API call that doesn't consume many credits
    params = {
        'module': 'stats',
        'action': 'ethprice',  # Works on most explorers
        'apikey': api_key
    }

    try:
        response = requests.get(api_url, params=params, timeout=10)
        data = response.json()

        if data.get('status') == '1':
            return True, "API is healthy"
        else:
            error_msg = data.get('message', 'Unknown API error')
            if 'rate limit' in error_msg.lower():
                return False, f"Rate limited: {error_msg}"
            elif 'invalid api key' in error_msg.lower():
                return False, f"Invalid API key: {error_msg}"
            else:
                return False, f"API error: {error_msg}"

    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"

def main():
    print(f"Blockchain Monitor API Health Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    config = load_config()
    if not config:
        print("Failed to load configuration. Exiting.")
        return

    api_keys = config.get('api_keys', {})
    if not api_keys:
        print("No API keys found in configuration.")
        return

    results = []

    for chain_id, api_key in api_keys.items():
        if not api_key or chain_id == 'default':
            continue

        print(f"Checking {chain_id.upper()} API...", end="", flush=True)
        is_healthy, message = check_api_health(chain_id, api_key)

        if is_healthy:
            print(" ✅ Healthy")
        else:
            print(f" ❌ Error: {message}")

        results.append({
            'chain_id': chain_id,
            'status': 'healthy' if is_healthy else 'error',
            'message': message
        })

    print("
Summary:")
    healthy_count = sum(1 for r in results if r['status'] == 'healthy')
    print(f"- {healthy_count}/{len(results)} APIs are healthy")

    if healthy_count < len(results):
        print("
Issues found:")
        for result in results:
            if result['status'] != 'healthy':
                print(f"- {result['chain_id'].upper()}: {result['message']}")

        print("
Troubleshooting tips:")
        print("1. Check your API keys in the secure configuration")
        print("2. Verify you haven't exceeded API rate limits")
        print("3. Check your network connection and proxy settings")
        print("4. Some APIs might be temporarily down - try again later")

if __name__ == "__main__":
    main()
