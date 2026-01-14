# src/arb/bybit_adapter.py

"""
Bybit adapter for price/orderbook data.
Based on Bybit V5 API - no authentication required for market data.
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger('blockchain_monitor.bybit')

BYBIT_REST_URL = "https://api.bybit.com"

# Trading fee: 0.1% = 0.001 (taker fee for spot)
BYBIT_TRADING_FEE = 0.001


def get_price(symbol: str) -> Optional[float]:
    """Get current price for a symbol (no auth required)."""
    try:
        resp = requests.get(
            f"{BYBIT_REST_URL}/v5/market/tickers",
            params={"category": "spot", "symbol": symbol.upper()},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                return float(data["result"]["list"][0].get("lastPrice", 0))
    except Exception as e:
        logger.error(f"Bybit price error for {symbol}: {e}")
    return None


def get_orderbook(symbol: str, limit: int = 5) -> Optional[dict]:
    """Get orderbook for a symbol (no auth required)."""
    try:
        resp = requests.get(
            f"{BYBIT_REST_URL}/v5/market/orderbook",
            params={"category": "spot", "symbol": symbol.upper(), "limit": limit},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("retCode") == 0:
                result = data.get("result", {})
                bids = result.get("b", [])
                asks = result.get("a", [])
                if bids and asks:
                    return {
                        "best_bid": float(bids[0][0]),
                        "best_ask": float(asks[0][0]),
                        "bid_qty": float(bids[0][1]),
                        "ask_qty": float(asks[0][1]),
                        "bids": [[float(b[0]), float(b[1])] for b in bids],
                        "asks": [[float(a[0]), float(a[1])] for a in asks],
                    }
    except Exception as e:
        logger.error(f"Bybit orderbook error for {symbol}: {e}")
    return None


def bybit_buy_cost_usdt(symbol: str, qty_tokens: float) -> float:
    """
    Approximate USDT cost to buy `qty_tokens` of `symbol` on Bybit, including fee.
    Walks through the order book to account for slippage on larger orders.
    """
    resp = requests.get(
        f"{BYBIT_REST_URL}/v5/market/orderbook",
        params={"category": "spot", "symbol": symbol.upper(), "limit": 50},
        timeout=10
    )
    data = resp.json()
    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit orderbook error: {data.get('retMsg')}")
    
    asks = data.get("result", {}).get("a", [])
    
    remaining_qty = qty_tokens
    total_cost = 0.0
    
    for price_str, qty_str in asks:
        if remaining_qty <= 0:
            break
        price = float(price_str)
        available_qty = float(qty_str)
        
        fill_qty = min(remaining_qty, available_qty)
        total_cost += price * fill_qty
        remaining_qty -= fill_qty
    
    # If not enough liquidity, estimate remaining at last price
    if remaining_qty > 0:
        last_price = float(asks[-1][0]) if asks else 0
        total_cost += last_price * remaining_qty
    
    fee = total_cost * BYBIT_TRADING_FEE
    return total_cost + fee


def bybit_sell_proceeds_usdt(symbol: str, qty_tokens: float) -> float:
    """
    Approximate USDT proceeds from selling `qty_tokens` of `symbol` on Bybit, after fee.
    Walks through the order book to account for slippage on larger orders.
    """
    resp = requests.get(
        f"{BYBIT_REST_URL}/v5/market/orderbook",
        params={"category": "spot", "symbol": symbol.upper(), "limit": 50},
        timeout=10
    )
    data = resp.json()
    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit orderbook error: {data.get('retMsg')}")
    
    bids = data.get("result", {}).get("b", [])
    
    remaining_qty = qty_tokens
    total_proceeds = 0.0
    
    for price_str, qty_str in bids:
        if remaining_qty <= 0:
            break
        price = float(price_str)
        available_qty = float(qty_str)
        
        fill_qty = min(remaining_qty, available_qty)
        total_proceeds += price * fill_qty
        remaining_qty -= fill_qty
    
    # If not enough liquidity, estimate remaining at last price
    if remaining_qty > 0:
        last_price = float(bids[-1][0]) if bids else 0
        total_proceeds += last_price * remaining_qty
    
    fee = total_proceeds * BYBIT_TRADING_FEE
    return total_proceeds - fee
