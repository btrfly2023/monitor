# src/arb/cex_dex_monitor.py
"""
Real-time CEX-DEX spread monitor.
Compares Binance prices with Ethereum DEX prices (via Odos) and alerts on arbitrage opportunities.

Uses shared adapters:
- binance_adapter for Binance price/orderbook
- dex_adapter for DEX quotes via Odos
"""

import time
import logging
import json
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from datetime import datetime

# Use shared adapters
from .binance_adapter import get_orderbook as binance_get_orderbook, BINANCE_TRADING_FEE
from .bybit_adapter import get_orderbook as bybit_get_orderbook, BYBIT_TRADING_FEE
from .dex_adapter import dex_sell_token_for_stable, dex_buy_token_from_stable

# WebSocket support (optional)
try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False

logger = logging.getLogger('blockchain_monitor.cex_dex')


@dataclass
class TokenConfig:
    """Configuration for a token to monitor."""
    name: str                      # e.g., "CVX CEX-DEX"
    symbol: str                    # e.g., "CVX"
    binance_symbol: str            # e.g., "CVXUSDT" (also used for Bybit symbol)
    dex_token_symbol: str          # Token symbol in TOKEN_ADDRESSES
    dex_stable_symbol: str         # Stable symbol in TOKEN_ADDRESSES
    chain_id: int = 1              # Default Ethereum mainnet
    fixed_usdt_amount: float = 1000  # Trade size in USD
    alert_threshold: float = 10.0    # USD profit for urgent alert
    info_threshold: float = 5.0      # USD profit for info message
    enabled: bool = True
    cex_type: str = "binance"      # "binance" or "bybit"


DEFAULT_TOKENS = [
    TokenConfig(
        name="CVX CEX-DEX",
        symbol="CVX",
        binance_symbol="CVXUSDT",
        dex_token_symbol="CVX",
        dex_stable_symbol="USDT",
        fixed_usdt_amount=1000,
        alert_threshold=10.0,
        info_threshold=5.0,
    ),
]


class BinanceWebSocket:
    """WebSocket-based real-time price streaming from Binance."""
    
    def __init__(self, symbols: List[str], on_price_update: Callable[[str, float, float], None]):
        """
        Args:
            symbols: List of symbols to subscribe (e.g., ["CVXUSDT"])
            on_price_update: Callback(symbol, bid, ask) called on each price update
        """
        if not WEBSOCKET_AVAILABLE:
            raise ImportError("websocket-client not installed")
        self.symbols = [s.lower() for s in symbols]
        self.on_price_update = on_price_update
        self.ws = None
        self.running = False
        self.thread = None
        self.prices: Dict[str, Dict] = {}
        
        streams = "/".join([f"{s}@bookTicker" for s in self.symbols])
        self.ws_url = f"wss://stream.binance.com:9443/stream?streams={streams}"
    
    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "data" in data:
                data = data["data"]
            symbol = data.get("s", "").upper()
            if "b" in data and "a" in data:
                bid = float(data["b"])
                ask = float(data["a"])
                self.prices[symbol] = {"bid": bid, "ask": ask, "ts": time.time()}
                if self.on_price_update:
                    self.on_price_update(symbol, bid, ask)
        except Exception as e:
            logger.debug(f"WS message parse error: {e}")
    
    def _on_error(self, ws, error):
        logger.error(f"Binance WS error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        logger.info(f"Binance WS closed: {close_status_code} {close_msg}")
        if self.running:
            logger.info("Reconnecting in 5s...")
            time.sleep(5)
            self._connect()
    
    def _on_open(self, ws):
        logger.info(f"Binance WS connected to {len(self.symbols)} streams")
    
    def _connect(self):
        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
        )
        self.ws.run_forever(ping_interval=30, ping_timeout=10)
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._connect, daemon=True)
        self.thread.start()
        logger.info("Binance WebSocket started")
    
    def stop(self):
        self.running = False
        if self.ws:
            self.ws.close()
    
    def get_price(self, symbol: str) -> Optional[Dict]:
        return self.prices.get(symbol.upper())


@dataclass
class SpreadResult:
    """Result of spread calculation."""
    token: str
    name: str
    binance_price: float
    dex_sell_price: float      # Price when selling token on DEX
    dex_buy_price: float       # Effective price when buying token on DEX
    spread_sell_dex_pct: float # % profit: buy Binance, sell DEX
    spread_buy_dex_pct: float  # % profit: buy DEX, sell Binance
    profit_sell_dex_usd: float # USD profit: buy Binance, sell DEX
    profit_buy_dex_usd: float  # USD profit: buy DEX, sell Binance
    best_direction: str        # "buy_dex" or "sell_dex"
    best_profit_usd: float
    trade_size_usd: float
    timestamp: datetime


class CexDexMonitor:
    """Monitors CEX-DEX spreads for arbitrage opportunities."""
    
    def __init__(self, tokens: List[TokenConfig] = None, 
                 on_alert: Callable[[SpreadResult, TokenConfig], None] = None,
                 on_info: Callable[[SpreadResult, TokenConfig], None] = None,
                 on_status: Callable[[List[SpreadResult]], None] = None,
                 use_websocket: bool = False,
                 status_interval_seconds: int = 600):
        self.tokens = tokens or DEFAULT_TOKENS
        self.on_alert = on_alert
        self.on_info = on_info
        self.on_status = on_status
        self.running = False
        self.last_results: Dict[str, SpreadResult] = {}
        self.status_interval_seconds = status_interval_seconds
        self.last_status_time = 0
        
        # WebSocket mode
        self.use_websocket = use_websocket
        self.binance_ws = None
        if use_websocket and WEBSOCKET_AVAILABLE:
            symbols = [t.binance_symbol for t in self.tokens if t.enabled]
            self.binance_ws = BinanceWebSocket(symbols, self._on_ws_price_update)
    
    def _on_ws_price_update(self, symbol: str, bid: float, ask: float):
        """Called on each WebSocket price update."""
        for token in self.tokens:
            if token.binance_symbol == symbol and token.enabled:
                self._check_spread_ws(token, bid, ask)
                break
    
    def _check_spread_ws(self, token: TokenConfig, binance_bid: float, binance_ask: float):
        """Check spread using WebSocket price."""
        binance_mid = (binance_bid + binance_ask) / 2
        token_amount = token.fixed_usdt_amount / binance_mid
        
        # Get DEX prices using shared adapter
        try:
            dex_sell_proceeds = dex_sell_token_for_stable(
                token.dex_token_symbol, token.dex_stable_symbol,
                token_amount, chain_id=token.chain_id
            )
            dex_sell_price = dex_sell_proceeds / token_amount
            
            tokens_from_dex = dex_buy_token_from_stable(
                token.dex_token_symbol, token.dex_stable_symbol,
                token.fixed_usdt_amount, chain_id=token.chain_id
            )
            dex_buy_price = token.fixed_usdt_amount / tokens_from_dex
        except Exception as e:
            logger.debug(f"DEX quote failed: {e}")
            return
        
        # Calculate profits
        buy_binance_cost = binance_ask * (1 + BINANCE_TRADING_FEE) * token_amount
        sell_dex_proceeds = dex_sell_price * token_amount
        profit_sell_dex_usd = sell_dex_proceeds - buy_binance_cost
        spread_sell_dex_pct = (profit_sell_dex_usd / buy_binance_cost) * 100
        
        buy_dex_cost = token.fixed_usdt_amount
        sell_binance_proceeds = binance_bid * (1 - BINANCE_TRADING_FEE) * tokens_from_dex
        profit_buy_dex_usd = sell_binance_proceeds - buy_dex_cost
        spread_buy_dex_pct = (profit_buy_dex_usd / buy_dex_cost) * 100
        
        best_direction = "sell_dex" if profit_sell_dex_usd > profit_buy_dex_usd else "buy_dex"
        best_profit_usd = max(profit_sell_dex_usd, profit_buy_dex_usd)
        
        result = SpreadResult(
            token=token.symbol, name=token.name, binance_price=binance_mid,
            dex_sell_price=dex_sell_price, dex_buy_price=dex_buy_price,
            spread_sell_dex_pct=spread_sell_dex_pct, spread_buy_dex_pct=spread_buy_dex_pct,
            profit_sell_dex_usd=profit_sell_dex_usd, profit_buy_dex_usd=profit_buy_dex_usd,
            best_direction=best_direction, best_profit_usd=best_profit_usd,
            trade_size_usd=token.fixed_usdt_amount, timestamp=datetime.now(),
        )
        self.last_results[token.symbol] = result
        
        # Check thresholds
        if best_profit_usd >= token.alert_threshold:
            logger.warning(f"ARB ALERT: {token.name} {best_direction} ${best_profit_usd:.2f}")
            if self.on_alert:
                self.on_alert(result, token)
        elif best_profit_usd >= token.info_threshold:
            logger.info(f"ARB INFO: {token.name} {best_direction} ${best_profit_usd:.2f}")
            if self.on_info:
                self.on_info(result, token)
    
    def start_websocket(self):
        """Start WebSocket streaming."""
        if self.binance_ws:
            self.binance_ws.start()
    
    def stop_websocket(self):
        """Stop WebSocket streaming."""
        if self.binance_ws:
            self.binance_ws.stop()
    
    def check_spread(self, token: TokenConfig) -> Optional[SpreadResult]:
        """Check spread for a single token using REST API."""
        if not token.enabled:
            return None
        
        # Get CEX price using appropriate adapter based on cex_type
        cex_type = getattr(token, 'cex_type', 'binance')
        if cex_type == "bybit":
            cex_ob = bybit_get_orderbook(token.binance_symbol)
            trading_fee = BYBIT_TRADING_FEE
        else:
            cex_ob = binance_get_orderbook(token.binance_symbol)
            trading_fee = BINANCE_TRADING_FEE
        
        if not cex_ob:
            return None
        
        cex_bid = cex_ob["best_bid"]
        cex_ask = cex_ob["best_ask"]
        cex_mid = (cex_bid + cex_ask) / 2
        token_amount = token.fixed_usdt_amount / cex_mid
        
        # Get DEX prices using shared adapter
        try:
            dex_sell_proceeds = dex_sell_token_for_stable(
                token.dex_token_symbol, token.dex_stable_symbol,
                token_amount, chain_id=token.chain_id
            )
            dex_sell_price = dex_sell_proceeds / token_amount
            
            tokens_from_dex = dex_buy_token_from_stable(
                token.dex_token_symbol, token.dex_stable_symbol,
                token.fixed_usdt_amount, chain_id=token.chain_id
            )
            dex_buy_price = token.fixed_usdt_amount / tokens_from_dex
        except Exception as e:
            logger.debug(f"DEX quote failed for {token.symbol}: {e}")
            return None
        
        # Calculate profits
        buy_cex_cost = cex_ask * (1 + trading_fee) * token_amount
        sell_dex_proceeds = dex_sell_price * token_amount
        profit_sell_dex_usd = sell_dex_proceeds - buy_cex_cost
        spread_sell_dex_pct = (profit_sell_dex_usd / buy_cex_cost) * 100
        
        buy_dex_cost = token.fixed_usdt_amount
        sell_cex_proceeds = cex_bid * (1 - trading_fee) * tokens_from_dex
        profit_buy_dex_usd = sell_cex_proceeds - buy_dex_cost
        spread_buy_dex_pct = (profit_buy_dex_usd / buy_dex_cost) * 100
        
        best_direction = "sell_dex" if profit_sell_dex_usd > profit_buy_dex_usd else "buy_dex"
        best_profit_usd = max(profit_sell_dex_usd, profit_buy_dex_usd)
        
        return SpreadResult(
            token=token.symbol, name=token.name, binance_price=cex_mid,
            dex_sell_price=dex_sell_price, dex_buy_price=dex_buy_price,
            spread_sell_dex_pct=spread_sell_dex_pct, spread_buy_dex_pct=spread_buy_dex_pct,
            profit_sell_dex_usd=profit_sell_dex_usd, profit_buy_dex_usd=profit_buy_dex_usd,
            best_direction=best_direction, best_profit_usd=best_profit_usd,
            trade_size_usd=token.fixed_usdt_amount, timestamp=datetime.now(),
        )
    
    def check_all(self, force_status: bool = False) -> List[SpreadResult]:
        """Check spreads for all configured tokens."""
        results = []
        for token in self.tokens:
            result = self.check_spread(token)
            if result:
                results.append(result)
                self.last_results[token.symbol] = result
                
                # Check thresholds and notify
                logger.debug(f"{token.name}: best_profit=${result.best_profit_usd:.2f}, threshold=${token.alert_threshold}")
                if result.best_profit_usd >= token.alert_threshold:
                    logger.warning(f"ARB ALERT: {token.name} {result.best_direction} ${result.best_profit_usd:.2f}")
                    if self.on_alert:
                        self.on_alert(result, token)
                elif result.best_profit_usd >= token.info_threshold:
                    logger.info(f"ARB INFO: {token.name} {result.best_direction} ${result.best_profit_usd:.2f}")
                    if self.on_info:
                        self.on_info(result, token)
        
        # Send status update periodically or if forced
        now = time.time()
        if force_status or (now - self.last_status_time >= self.status_interval_seconds):
            self.last_status_time = now
            if self.on_status and results:
                self.on_status(results)
        
        return results
    
    def print_spreads(self, results: List[SpreadResult] = None):
        """Print current spreads."""
        results = results or list(self.last_results.values())
        print(f"\n{'='*90}")
        print(f"CEX-DEX Spread Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*90}")
        print(f"{'Token':<8} {'Binance':>10} {'DEX Sell':>10} {'DEX Buy':>10} {'$Sell DEX':>10} {'$Buy DEX':>10} {'Size':>8}")
        print(f"{'-'*90}")
        for r in results:
            sell_mark = "**" if r.profit_sell_dex_usd > 10 else "*" if r.profit_sell_dex_usd > 5 else "  "
            buy_mark = "**" if r.profit_buy_dex_usd > 10 else "*" if r.profit_buy_dex_usd > 5 else "  "
            print(f"{r.token:<8} ${r.binance_price:>9.4f} ${r.dex_sell_price:>9.4f} ${r.dex_buy_price:>9.4f} "
                  f"${r.profit_sell_dex_usd:>8.2f}{sell_mark} ${r.profit_buy_dex_usd:>8.2f}{buy_mark} ${r.trade_size_usd:>6.0f}")
        print(f"{'='*90}\n")
    
    def run(self, interval_seconds: float = 10, print_interval: int = 6):
        """Run continuous monitoring."""
        self.running = True
        iteration = 0
        logger.info(f"Starting CEX-DEX monitor for {len(self.tokens)} tokens")
        
        while self.running:
            try:
                results = self.check_all()
                iteration += 1
                
                if iteration % print_interval == 0:
                    self.print_spreads(results)
                
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                logger.info("Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(interval_seconds)
    
    def stop(self):
        """Stop monitoring."""
        self.running = False


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="CEX-DEX Spread Monitor")
    parser.add_argument("--interval", "-i", type=float, default=10, help="Check interval in seconds (REST mode)")
    parser.add_argument("--size", "-s", type=float, default=1000, help="Trade size in USD")
    parser.add_argument("--alert", "-a", type=float, default=10, help="Alert threshold in USD")
    parser.add_argument("--info", type=float, default=5, help="Info threshold in USD")
    parser.add_argument("--websocket", "-w", action="store_true", help="Use WebSocket for real-time prices")
    args = parser.parse_args()
    
    # Update token configs
    for token in DEFAULT_TOKENS:
        token.fixed_usdt_amount = args.size
        token.alert_threshold = args.alert
        token.info_threshold = args.info
    
    def on_alert(result: SpreadResult, token: TokenConfig):
        print(f"\n*** ARB ALERT: {token.name} ***")
        print(f"    Direction: {result.best_direction}")
        print(f"    Profit: ${result.best_profit_usd:.2f}")
        print(f"    Trade Size: ${result.trade_size_usd:.0f}")
        print(f"    Binance: ${result.binance_price:.4f}")
        print(f"    DEX Sell: ${result.dex_sell_price:.4f}")
        print(f"    DEX Buy: ${result.dex_buy_price:.4f}")
    
    def on_info(result: SpreadResult, token: TokenConfig):
        print(f"\n[INFO] {token.name}: {result.best_direction} ${result.best_profit_usd:.2f}")
    
    monitor = CexDexMonitor(on_alert=on_alert, on_info=on_info, use_websocket=args.websocket)
    
    # Initial check
    print(f"Checking spreads (size: ${args.size}, alert: ${args.alert}, info: ${args.info})...")
    results = monitor.check_all()
    monitor.print_spreads(results)
    
    if args.websocket:
        print(f"Starting WebSocket mode (real-time price streaming)...")
        monitor.start_websocket()
        try:
            while True:
                time.sleep(60)
                monitor.print_spreads()
        except KeyboardInterrupt:
            monitor.stop_websocket()
            print("\nStopped.")
    else:
        print(f"Starting REST polling mode (interval: {args.interval}s)...")
        monitor.run(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
