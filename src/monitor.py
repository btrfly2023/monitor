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
import asyncio

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.notifiers.telegram import TelegramNotifier
from src.alerts.alert_system import AlertSystem
import dotenv
from src.tokens.token_monitor import monitor_token_swaps
from src.arb.arb_finder import (
    find_arb_for_qty,
    pretty_print_scenarios,
    ArbConfig,
)

# Import CEX-DEX monitor
try:
    from src.arb.cex_dex_monitor import CexDexMonitor, TokenConfig, SpreadResult
    CEX_DEX_AVAILABLE = True
except ImportError:
    CEX_DEX_AVAILABLE = False
    logging.warning("CEX-DEX monitor not available")

# Import hot wallet monitor
try:
    from src.monitors.hot_wallet_monitor import HotWalletMonitor
    HOT_WALLET_AVAILABLE = True
except ImportError:
    HOT_WALLET_AVAILABLE = False
    logging.warning("Hot wallet monitor not available (missing dependencies)")

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
    def __init__(self, config_path, swap_config_path):
        self.config_path = config_path
        self.swap_config_path = swap_config_path
        self.load_config()
        self.setup_notifiers()
        self.alert_system = AlertSystem(self.config, self.notifiers)
        self.previous_results = {}
        self.value_history = {}  # Track recent values to detect flip states

        # Other initialization
        self.last_update_time = 0
        self.update_interval = 600  # 10 minutes in seconds

        # Hot wallet monitor
        self.hot_wallet_monitor = None
        self.hot_wallet_thread = None
        self.hot_wallet_loop = None
        
        # CEX-DEX monitor
        self.cex_dex_monitor = None
        self.cex_dex_thread = None
        self.cex_dex_running = False

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

            # Load swap configuration
            with open(self.swap_config_path, 'r') as f:
                self.swap_config = json.load(f)
            logger.info(f"Swap configuration loaded from {self.swap_config_path}")

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
            self.config['notifications']['telegram']['bot_token'] = os.getenv('TELEGRAM_BOT_TOKEN')
        if os.getenv('TELEGRAM_CHAT_ID'):
            self.config['notifications']['telegram']['chat_id'] = os.getenv('TELEGRAM_CHAT_ID')
        if os.getenv('TELEGRAM_BOT_TOKEN_2'):
            self.config['notifications']['telegram']['bot_token_2'] = os.getenv('TELEGRAM_BOT_TOKEN_2')
        if os.getenv('TELEGRAM_CHAT_ID_2'):
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

    def send_telegram_notification_sync(self, message):
        """Synchronous wrapper for sending Telegram notifications"""
        try:
            telegram = self.notifiers.get('telegram')
            if telegram:
                telegram.send_message(message, urgent=True)
                logger.info("Hot wallet notification sent via Telegram")
        except Exception as e:
            logger.error(f"Failed to send hot wallet notification: {e}")

    def get_chain_api_url(self, chain_name):
        chain_configs = {
            'ethereum': 'https://api.etherscan.io/v2/api',
            'polygon': 'https://api.polygonscan.com/api',
            'bsc': 'https://api.bscscan.com/api',
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
                    if isinstance(result, dict):
                        if "ProposeGasPrice" in result:
                            result = round(float(result["ProposeGasPrice"]), 2)
                    else:
                        result = round(float(result)/1e18, 2)

                    # Check for changes
                    previous = self.previous_results.get(query_id)
                    logger.info(f"~~~query {query_id}: {result}")

                    if previous is not None and previous != result:
                        # Check for flip state - detect oscillation between values
                        # A flip is when BOTH the previous and current values have been seen recently
                        # This catches API inconsistency where values bounce between states
                        history = self.value_history.get(query_id, [])
                        is_flip = result in history and previous in history
                        
                        if is_flip:
                            logger.warning(f"Flip state detected for {query_id}: {previous} -> {result} (oscillating between known values, skipping alert)")
                        else:
                            logger.info(f"Change detected for query {query_id}")
                            # Process alerts
                            self.alert_system.process_alert(query_id, result, previous)

                    # Update value history (keep last 5 values)
                    if query_id not in self.value_history:
                        self.value_history[query_id] = []
                    self.value_history[query_id].append(result)
                    if len(self.value_history[query_id]) > 5:
                        self.value_history[query_id].pop(0)

                    # Store the new result
                    self.previous_results[query_id] = result
                    return result
                else:
                    error_msg = data.get('message', 'Unknown API error')
                    logger.error(f"API error for query {query_id}: {error_msg}")

                    if "rate limit" in error_msg.lower():
                        wait_time = retry_delay * (2 ** retry)
                        logger.warning(f"Rate limit hit, waiting {wait_time} seconds before retry")
                        time.sleep(wait_time)
                        continue
                    return None

            except requests.exceptions.ProxyError as e:
                logger.error(f"Proxy error for query {query_id}: {e}")
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
            results = monitor_token_swaps(self.swap_config["monitor_pairs"])

            # Send summary to Telegram
            telegram = self.notifiers['telegram']
            telegram.send_message_second_bot(results["summary"])

            # Send notifications for significant changes
            if results["notifications"]:
                for notification in results["notifications"]:
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
            query_results = self.previous_results
            telegram = self.notifiers['telegram']

            if query_results and telegram:
                logger.info(f"Sent periodic update via second bot: {query_results}")
                telegram.send_blockchain_update(query_results)
                logger.info("Sent periodic update via second bot")
            else:
                logger.warning("No data available for periodic update")
        except Exception as e:
            logger.error(f"Error sending periodic update: {e}")

    def start_hot_wallet_monitor_thread(self):
        """Start hot wallet monitor in a separate thread with its own event loop"""
        if not HOT_WALLET_AVAILABLE:
            logger.warning("Hot wallet monitor dependencies not installed, skipping")
            return

        hw_config = self.config.get('hot_wallet_monitor', {})

        if not hw_config.get('enabled', False):
            logger.info("Hot wallet monitor is disabled in config")
            return

        # Get WebSocket URL
        ws_url = os.getenv('WEBSOCKET_RPC_URL') or hw_config.get('websocket_rpc_url')

        if not ws_url or 'WEBSOCKET_API_KEY' in ws_url:
            logger.warning("Hot wallet monitor: WebSocket URL not configured properly")
            return

        # Get token thresholds
        token_thresholds = hw_config.get('token_thresholds', {})
        token_thresholds = {k.lower(): float(v) for k, v in token_thresholds.items()}

        if not token_thresholds:
            logger.warning("Hot wallet monitor: No token thresholds configured")
            return

        logger.info(f"Starting hot wallet monitor with {len(token_thresholds)} tokens")

        def run_async_monitor():
            """Run the async monitor in a new event loop"""
            # Create a new event loop for this thread
            self.hot_wallet_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.hot_wallet_loop)

            try:
                # Create notification callback that works with the sync telegram notifier
                def notification_callback_sync(message):
                    """Sync wrapper for notification callback"""
                    self.send_telegram_notification_sync(message)
                    return asyncio.sleep(0)  # Return a coroutine

                # Initialize monitor
                self.hot_wallet_monitor = HotWalletMonitor(
                    ws_url=ws_url,
                    token_thresholds=token_thresholds,
                    notification_callback=notification_callback_sync,
                    alert_cooldown_minutes=60  # Configurable cooldown in minutes
                )

                # Run the monitor
                self.hot_wallet_loop.run_until_complete(self.hot_wallet_monitor.start())
            except Exception as e:
                logger.error(f"Hot wallet monitor error: {e}", exc_info=True)
            finally:
                self.hot_wallet_loop.close()

        # Start in a daemon thread so it doesn't prevent shutdown
        self.hot_wallet_thread = threading.Thread(target=run_async_monitor, daemon=True)
        self.hot_wallet_thread.start()
        logger.info("Hot wallet monitor thread started")

    def _build_arb_config(self, monitor_config: dict) -> ArbConfig:
        """
        Build ArbConfig from monitor configuration.
        Supports both CEX-DEX and DEX-DEX arbitrage.
        """
        arb_type = monitor_config.get('type', 'cex-dex')  # 'cex-dex' or 'dex-dex'

        if arb_type == 'cex-dex':
            # Legacy CEX-DEX config
            return ArbConfig(
                venue1_type='cex',
                venue1_token_symbol=monitor_config.get('binance_token_symbol'),
                venue1_symbol=monitor_config.get('binance_symbol'),
                venue2_type='dex',
                venue2_token_symbol=monitor_config.get('dex_token_symbol'),
                venue2_chain_id=monitor_config.get('dex_chain_id', 1),
                venue2_stable_symbol=monitor_config.get('dex_stable_symbol', 'USDT'),
                description_prefix=monitor_config.get('name', ''),
                use_testnet=monitor_config.get('use_testnet', False),
            )
        elif arb_type == 'dex-dex':
            # DEX-DEX config
            return ArbConfig(
                venue1_type='dex',
                venue1_token_symbol=monitor_config.get('venue1_token_symbol'),
                venue1_chain_id=monitor_config.get('venue1_chain_id'),
                venue1_stable_symbol=monitor_config.get('venue1_stable_symbol'),
                venue2_type='dex',
                venue2_token_symbol=monitor_config.get('venue2_token_symbol'),
                venue2_chain_id=monitor_config.get('venue2_chain_id'),
                venue2_stable_symbol=monitor_config.get('venue2_stable_symbol'),
                description_prefix=monitor_config.get('name', ''),
                use_testnet=False,
            )
        else:
            raise ValueError(f"Unknown arb type: {arb_type}")

    def check_arb_opportunities(self):
        """
        Check arbitrage opportunities for multiple configured pairs.

        Supports:
        - CEX-DEX arbitrage (Binance <-> Ethereum DEX)
        - DEX-DEX arbitrage (Ethereum DEX <-> Another chain DEX)
        """
        try:
            settings = self.config.get('settings', {})
            telegram = self.notifiers.get('telegram')

            if not telegram:
                logger.warning("No Telegram notifier configured; skipping arb alerts")
                return False

            # Check if we have multiple arb monitors configured
            arb_monitors = settings.get('arb_monitors', [])

            # Fallback to legacy single CEX-DEX config if arb_monitors is empty
            if not arb_monitors:
                logger.info("Using legacy single CEX-DEX arb config")
                arb_monitors = [{
                    "type": "cex-dex",
                    "name": "FXS",
                    "binance_symbol": settings.get('arb_binance_symbol', "FXSUSDT"),
                    "dex_token_symbol": settings.get('arb_dex_token_symbol', "WFRAX"),
                    "binance_token_symbol": settings.get('arb_binance_token_symbol', "FXS"),
                    "dex_stable_symbol": settings.get('arb_dex_stable_symbol', "USDT"),
                    "dex_chain_id": settings.get('arb_dex_chain_id', 1),
                    "fixed_token_qty": float(settings.get('arb_fixed_token_qty', 2000.0)),
                    "fixed_usdt_amount": float(settings.get('arb_fixed_usdt_amount', 2000.0)),
                    "alert_threshold": float(settings.get('arb_alert_threshold', 10.0)),
                    "info_threshold": float(settings.get('arb_info_threshold', 5.0)),
                    "use_testnet": bool(settings.get('arb_use_testnet', False)),
                    "enabled": True
                }]

            total_big_opps = 0
            total_info_opps = 0

            # Process each arb monitor
            for monitor_config in arb_monitors:
                if not monitor_config.get('enabled', True):
                    logger.info(f"Arb monitor '{monitor_config.get('name', 'unknown')}' is disabled, skipping")
                    continue

                name = monitor_config.get('name', 'Unknown')
                arb_type = monitor_config.get('type', 'cex-dex')

                qty_token = float(monitor_config.get('fixed_token_qty', 2000.0))
                usdt_amount = float(monitor_config.get('fixed_usdt_amount', 2000.0))

                alert_threshold = float(monitor_config.get('alert_threshold', 10.0))
                info_threshold = float(monitor_config.get('info_threshold', 5.0))

                if info_threshold >= alert_threshold:
                    logger.warning(
                        f"[{name}] info_threshold >= alert_threshold; "
                        f"adjust your config so info < alert."
                    )

                logger.info(f"Checking {arb_type} arb opportunities for {name}")

                try:
                    arb_config = self._build_arb_config(monitor_config)

                    scenarios = find_arb_for_qty(
                        qty_token=qty_token,
                        usdt_amount=usdt_amount,
                        config=arb_config,
                    )

                    # Already sorted by profit (low -> high)
                    pretty_print_scenarios(scenarios, min_profit=info_threshold)

                    # Two-level handling
                    big_opps = []
                    info_opps = []

                    for s in scenarios:
                        p = s.profit_usdt
                        if p > alert_threshold:
                            big_opps.append(s)
                        elif p > info_threshold:
                            info_opps.append(s)

                    # 1) Big opportunities (urgent alerts)
                    for s in big_opps:
                        msg = (
                            f"*ARB ALERT - {name}*\n\n"
                            f"*Type:* {arb_type}\n"
                            f"*Starting Amount:* `{usdt_amount:.2f}` USDT\n"
                            f"*Profit:* `{s.profit_usdt:.6f}` USDT\n\n"
                            f"*Scenario:* {s.description}\n\n"
                            f"*Leg 1:*\n`{s.leg1}`\n\n"
                        )
                        if s.leg2:
                            msg += f"*Leg 2:*\n`{s.leg2}`\n\n"
                        if s.leg3:
                            msg += f"*Leg 3:*\n`{s.leg3}`\n"
                        telegram.send_message(msg, urgent=True)

                    # 2) Info-only opportunities (non-urgent)
                    for s in info_opps:
                        msg = (
                            f"Arb info - {name} ({arb_type}):\n"
                            f"Starting: {usdt_amount:.2f} USDT\n"
                            f"Profit: {s.profit_usdt:.6f} USDT\n"
                            f"Scenario: {s.description}\n"
                            f"Leg 1: {s.leg1}\n"
                        )
                        if s.leg2:
                            msg += f"Leg 2: {s.leg2}\n"
                        if s.leg3:
                            msg += f"Leg 3: {s.leg3}\n"
                        telegram.send_message_second_bot(msg)

                    total_big_opps += len(big_opps)
                    total_info_opps += len(info_opps)

                    if big_opps or info_opps:
                        logger.info(
                            f"[{name}] Arb check done. Big: {len(big_opps)}, Info: {len(info_opps)}"
                        )
                    else:
                        logger.info(f"[{name}] Arb check done. No profitable opportunities.")

                except Exception as e:
                    logger.error(f"Error checking arb for {name}: {e}", exc_info=True)
                    continue

            logger.info(
                f"All arb checks complete. Total Big: {total_big_opps}, Total Info: {total_info_opps}"
            )
            return True

        except Exception as e:
            logger.error(f"Error in check_arb_opportunities: {e}", exc_info=True)
            return False

    def start_cex_dex_monitor_thread(self):
        """Start CEX-DEX monitor in a separate thread"""
        if not CEX_DEX_AVAILABLE:
            logger.warning("CEX-DEX monitor not available, skipping")
            return

        cex_dex_config = self.config.get('settings', {}).get('cex_dex_monitors', [])
        if not cex_dex_config:
            logger.info("No CEX-DEX monitors configured, skipping")
            return

        telegram = self.notifiers.get('telegram')

        def on_alert(result: SpreadResult, token: TokenConfig):
            msg = (
                f"*CEX-DEX ARB ALERT - {token.name}*\n\n"
                f"*Direction:* {result.best_direction}\n"
                f"*Profit:* `${result.best_profit_usd:.2f}`\n"
                f"*Trade Size:* `${result.trade_size_usd:.0f}`\n\n"
                f"*Binance:* `${result.binance_price:.4f}`\n"
                f"*DEX Sell:* `${result.dex_sell_price:.4f}`\n"
                f"*DEX Buy:* `${result.dex_buy_price:.4f}`"
            )
            if telegram:
                telegram.send_message(msg, urgent=True)

        def on_info(result: SpreadResult, token: TokenConfig):
            msg = (
                f"CEX-DEX arb info - {token.name}:\n"
                f"Direction: {result.best_direction}\n"
                f"Profit: ${result.best_profit_usd:.2f}\n"
                f"Trade Size: ${result.trade_size_usd:.0f}"
            )
            if telegram:
                telegram.send_message_second_bot(msg)

        def on_status(results: list):
            """Send periodic status update to info channel."""
            lines = ["CEX-DEX Monitor Status:"]
            for r in results:
                lines.append(f"  {r.name}: Binance ${r.binance_price:.4f}, DEX ${r.dex_sell_price:.4f}")
                lines.append(f"    Sell DEX: ${r.profit_sell_dex_usd:.2f}, Buy DEX: ${r.profit_buy_dex_usd:.2f}")
            msg = "\n".join(lines)
            if telegram:
                telegram.send_message_second_bot(msg)

        # Build token configs from settings
        tokens = []
        for cfg in cex_dex_config:
            if not cfg.get('enabled', True):
                continue
            tokens.append(TokenConfig(
                name=cfg.get('name', ''),
                symbol=cfg.get('symbol', ''),
                binance_symbol=cfg.get('binance_symbol', ''),
                dex_token_address=cfg.get('dex_token_address', ''),
                dex_stable_address=cfg.get('dex_stable_address', ''),
                dex_stable_symbol=cfg.get('dex_stable_symbol', 'USDT'),
                chain_id=cfg.get('chain_id', 1),
                fixed_usdt_amount=cfg.get('fixed_usdt_amount', 1000),
                alert_threshold=cfg.get('alert_threshold', 10.0),
                info_threshold=cfg.get('info_threshold', 5.0),
            ))

        if not tokens:
            logger.info("No enabled CEX-DEX monitors, skipping")
            return

        status_interval = self.config.get('settings', {}).get('cex_dex_status_interval_seconds', 600)
        self.cex_dex_monitor = CexDexMonitor(
            tokens=tokens, on_alert=on_alert, on_info=on_info, on_status=on_status,
            status_interval_seconds=status_interval
        )
        interval = self.config.get('settings', {}).get('cex_dex_interval_seconds', 10)

        def run_cex_dex_monitor():
            logger.info(f"Starting CEX-DEX monitor with {len(tokens)} tokens, interval {interval}s")
            self.cex_dex_running = True
            first_run = True
            while self.cex_dex_running:
                try:
                    self.cex_dex_monitor.check_all(force_status=first_run)
                    first_run = False
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"CEX-DEX monitor error: {e}")
                    time.sleep(interval)

        self.cex_dex_thread = threading.Thread(target=run_cex_dex_monitor, daemon=True)
        self.cex_dex_thread.start()
        logger.info("CEX-DEX monitor thread started")

    def start(self):
        logger.info("Starting blockchain monitor")

        # Hot wallet monitor disabled
        # self.start_hot_wallet_monitor_thread()
        
        # Start CEX-DEX monitor thread
        self.start_cex_dex_monitor_thread()

        # Run immediately on start
        self.run_queries()
        self.check_token_rates()
        self.check_arb_opportunities()

        # Schedule regular runs
        interval_minutes = self.config.get('settings', {}).get('interval_minutes', 1)
        schedule.every(interval_minutes).minutes.do(self.run_queries)
        schedule.every(20 * interval_minutes).minutes.do(self.check_token_rates)

        # Arb checks: e.g. every 5 * interval_minutes
        arb_interval = self.config.get('settings', {}).get('arb_interval_minutes', 5 * interval_minutes)
        schedule.every(arb_interval).minutes.do(self.check_arb_opportunities)

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
            self.stop()
        except Exception as e:
            logger.error(f"Monitor stopped due to error: {e}")
            self.stop()
            raise

    def stop(self):
        """Clean shutdown of all monitors"""
        logger.info("Shutting down monitors...")

        # Stop CEX-DEX monitor
        self.cex_dex_running = False

        # Stop hot wallet monitor
        if self.hot_wallet_monitor and self.hot_wallet_loop:
            try:
                # Schedule the stop coroutine in the monitor's event loop
                asyncio.run_coroutine_threadsafe(
                    self.hot_wallet_monitor.stop(), 
                    self.hot_wallet_loop
                )
                # Give it a moment to clean up
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error stopping hot wallet monitor: {e}")

        logger.info("Shutdown complete")


if __name__ == "__main__":
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config',
        'blockchain_config.json'
    )

    swap_config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config',
        'token_swap_config.json'
    )

    monitor = BlockchainMonitor(config_path, swap_config_path)
    monitor.start()