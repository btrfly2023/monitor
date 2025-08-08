#!/usr/bin/env python3
import json
import os
import sys
import time
import schedule
import requests
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import threading
import logging

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.notifiers.telegram import TelegramNotifier
from src.alerts.alert_system import AlertSystem
import dotenv

from src.monitor_integration import run_token_monitoring


# Set up logging
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Configure rotating file handler (10MB max size, keep 5 backup files)
log_file = os.path.join(log_dir, 'blockchain_monitor.log')
handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        handler,
        logging.StreamHandler()  # Also log to console
    ]
)
logger = logging.getLogger('blockchain_monitor')

class BlockchainMonitor:
    def __init__(self, config_path):
        self.config_path = config_path
        self.load_config()
        self.setup_notifiers()
        self.alert_system = AlertSystem(self.config, self.notifiers)
        self.previous_results = {}

        # Other initialization
        self.last_update_time = 0
        self.update_interval = 600  # 5 minutes in seconds

    def load_config(self):
        try:
            # Load environment variables from .env file if it exists
            dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
            if os.path.exists(dotenv_path):
                dotenv.load_dotenv(dotenv_path)
                logger.info(f"Loaded environment variables from {dotenv_path}")

            # Load main configuration
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            logger.info(f"Configuration loaded from {self.config_path}")

            # Load secure keys if available
            secure_dir = os.path.join(os.path.dirname(self.config_path), 'secure')
            secure_keys_path = os.path.join(secure_dir, 'keys.json')

            if os.path.exists(secure_keys_path):
                with open(secure_keys_path, 'r') as f:
                    secure_keys = json.load(f)
                logger.info(f"Secure keys loaded from {secure_keys_path}")

                # Merge secure keys into config
                if 'api_keys' in secure_keys:
                    self.config['api_keys'] = secure_keys['api_keys']
                if 'notifications' in secure_keys:
                    self.config['notifications'] = secure_keys['notifications']
            else:
                logger.info("No secure keys file found, checking environment variables")

            # Override with environment variables if available
            self._load_from_env()

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            sys.exit(1)

    def _load_from_env(self):
        """Load configuration from environment variables."""
        # API Keys
        if 'api_keys' not in self.config:
            self.config['api_keys'] = {}

        if os.getenv('ETHERSCAN_API_KEY'):
            self.config['api_keys']['ethereum'] = os.getenv('ETHERSCAN_API_KEY')
        if os.getenv('POLYGONSCAN_API_KEY'):
            self.config['api_keys']['polygon'] = os.getenv('POLYGONSCAN_API_KEY')
        if os.getenv('BSCSCAN_API_KEY'):
            self.config['api_keys']['bsc'] = os.getenv('BSCSCAN_API_KEY')
        if os.getenv('DEFAULT_API_KEY'):
            self.config['api_keys']['default'] = os.getenv('DEFAULT_API_KEY')

        # Telegram settings
        if 'notifications' not in self.config:
            self.config['notifications'] = {}
        if 'telegram' not in self.config['notifications']:
            self.config['notifications']['telegram'] = {}

        if os.getenv('TELEGRAM_BOT_TOKEN'):
            if 'telegram' not in self.config['notifications']:
                self.config['notifications']['telegram'] = {}
            self.config['notifications']['telegram']['bot_token'] = os.getenv('TELEGRAM_BOT_TOKEN')

        if os.getenv('TELEGRAM_CHAT_ID'):
            if 'telegram' not in self.config['notifications']:
                self.config['notifications']['telegram'] = {}
            self.config['notifications']['telegram']['chat_id'] = os.getenv('TELEGRAM_CHAT_ID')

        if os.getenv('TELEGRAM_BOT_TOKEN_2'):
            if 'telegram' not in self.config['notifications']:
                self.config['notifications']['telegram'] = {}
            self.config['notifications']['telegram']['bot_token_2'] = os.getenv('TELEGRAM_BOT_TOKEN_2')

        if os.getenv('TELEGRAM_CHAT_ID_2'):
            if 'telegram' not in self.config['notifications']:
                self.config['notifications']['telegram'] = {}
            self.config['notifications']['telegram']['chat_id_2'] = os.getenv('TELEGRAM_CHAT_ID_2')

        # Proxy settings
        if os.getenv('PROXY_URL'):
            if 'settings' not in self.config:
                self.config['settings'] = {}
            self.config['settings']['use_proxy'] = True
            self.config['settings']['proxy_url'] = os.getenv('PROXY_URL')

    def setup_notifiers(self):
        self.notifiers = {}

        # Set up Telegram notifier if configured
        if 'telegram' in self.config.get('notifications', {}):
            telegram_config = self.config['notifications']['telegram']
            self.notifiers['telegram'] = TelegramNotifier(
                token=telegram_config.get('bot_token'),
                chat_id=telegram_config.get('chat_id'),
                second_token=telegram_config.get('bot_token_2'),
                second_chat_id=telegram_config.get('chat_id_2')
            )
            logger.info("Telegram notifier configured")

    def get_chain_api_url(self, chain_name):
        chain_configs = {
            'ethereum': 'https://api.etherscan.io/v2/api',
            'polygon': 'https://api.polygonscan.com/api',
            'bsc': 'https://api.bscscan.com/api',
            # Add more chains as needed
        }
        return chain_configs.get(chain_name, 'https://api.etherscan.io/api')

    def get_api_key(self, chain_name):
        api_keys = self.config.get('api_keys', {})
        return api_keys.get(chain_name, api_keys.get('default', ''))

    def execute_query(self, query):
        query_id = query.get('id', 'unknown')
        chain_name = query.get('chain_name', 'ethereum')
        api_url = self.get_chain_api_url(chain_name)
        api_key = self.get_api_key(chain_name)

        params = query.get('params', {}).copy()
        params['apikey'] = api_key

        # Get proxy settings from config or environment
        proxies = None
        if self.config.get('settings', {}).get('use_proxy', False):
            proxy_url = self.config.get('settings', {}).get('proxy_url', None)
            if proxy_url:
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
                logger.debug(f"Using proxy: {proxy_url}")

        # Add exponential backoff for retries
        max_retries = self.config.get('settings', {}).get('max_retries', 3)
        retry_delay = self.config.get('settings', {}).get('retry_delay_seconds', 2)

        for retry in range(max_retries):
            try:
                logger.debug(f"Executing query {query_id} on {chain_name} (attempt {retry+1}/{max_retries})")

                # Try without proxy first if we're having proxy issues
                if retry > 0 and proxies:
                    logger.debug(f"Retry attempt {retry+1}: trying without proxy")
                    response = requests.get(api_url, params=params, timeout=30)
                else:
                    response = requests.get(api_url, params=params, proxies=proxies, timeout=30)

                response.raise_for_status()
                data = response.json()

                if data.get('status') == '1':
                    result = data.get('result')
                    # hack, round to 2
                    if isinstance(result, str):
                        result = round(float(result)/1e18, 2)

                    # Check for changes
                    previous = self.previous_results.get(query_id)
                    logger.info(f"~~~query {query_id}: {result}")
                    if previous is not None and previous != result:
                        logger.info(f"Change detected for query {query_id}")

                        # Process alerts
                        self.alert_system.process_alert(query_id, result, previous)

                    # Store the new result
                    self.previous_results[query_id] = result
                    return result
                else:
                    error_msg = data.get('message', 'Unknown API error')
                    logger.error(f"API error for query {query_id}: {error_msg}")

                    # If we're being rate limited, wait longer before retry
                    if "rate limit" in error_msg.lower():
                        wait_time = retry_delay * (2 ** retry)
                        logger.warning(f"Rate limit hit, waiting {wait_time} seconds before retry")
                        time.sleep(wait_time)
                        continue

                    return None

            except requests.exceptions.ProxyError as e:
                logger.error(f"Proxy error for query {query_id}: {e}")
                # Try again without proxy on next iteration
                proxies = None
                time.sleep(retry_delay)
                continue

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed for query {query_id}: {e}")
                wait_time = retry_delay * (2 ** retry)
                logger.debug(f"Waiting {wait_time} seconds before retry")
                time.sleep(wait_time)
                continue

            except Exception as e:
                logger.error(f"Unexpected error for query {query_id}: {e}")
                return None

        logger.error(f"All retry attempts failed for query {query_id}")
        return None

    def check_token_rates(self):
        """Check token rates and send notifications via Telegram"""
        try:
            # Run token monitoring
            results = run_token_monitoring()
            
            # Send summary to Telegram
            telegram = self.notifiers['telegram'] 
            telegram.send_message_second_bot(results["summary"])
            
            # Send notifications for significant changes
            # print(results)
            if results["notifications"]:
                for notification in results["notifications"]:
                    # self.send_message_second_bot(f"🚨 ALERT: {notification['message']}")
                    telegram.send_message(f"🚨 ALERT: {notification['message']}", True)
            
            return True
        except Exception as e:
            logger.error(f"Error checking token rates: {str(e)}")
            return False

    def run_queries(self):
        logger.info("Running scheduled queries")
        successful_queries = 0
        failed_queries = 0

        for query in self.config.get('queries', []):
            query_id = query.get('id', 'unknown')
            try:
                logger.debug(f"Starting query: {query_id}")
                result = self.execute_query(query)

                if result is not None:
                    successful_queries += 1
                    logger.debug(f"Query {query_id} completed successfully")
                else:
                    failed_queries += 1
                    logger.warning(f"Query {query_id} returned no results")
            except Exception as e:
                failed_queries += 1
                logger.error(f"Unhandled exception in query {query_id}: {e}", exc_info=True)
                # Continue with next query despite this error
                continue

        logger.info(f"Query batch completed. Success: {successful_queries}, Failed: {failed_queries}")
        # Check if it's time for a periodic update
        current_time = time.time()
        if current_time - self.last_update_time >= self.update_interval:
            self.send_periodic_update()
            self.last_update_time = current_time 

    def send_periodic_update(self):
        """Send periodic blockchain data update via second bot."""
        try:
            # Fetch blockchain data
            query_results = self.previous_results  # Adjust to your actual method

            # Send to second bot
            telegram = self.notifiers['telegram'] 
            if query_results and telegram:
                logger.info(f"Sent periodic update via second bot: {query_results}")
                telegram.send_blockchain_update(query_results)
                logger.info("Sent periodic update via second bot")
            else:
                logger.warning("No data available for periodic update")

        except Exception as e:
            logger.error(f"Error sending periodic update: {e}")

    def start(self):
        logger.info("Starting blockchain monitor")

        # Run immediately on start
        self.run_queries()
        self.check_token_rates()

        # Schedule regular runs
        interval_minutes = self.config.get('settings', {}).get('interval_minutes', 1)
        schedule.every(interval_minutes).minutes.do(self.run_queries)
        schedule.every(20 * interval_minutes).minutes.do(self.check_token_rates)

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
        except Exception as e:
            logger.error(f"Monitor stopped due to error: {e}")
            raise

if __name__ == "__main__":
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config',
        'blockchain_config.json'
    )

    monitor = BlockchainMonitor(config_path)
    monitor.start()


