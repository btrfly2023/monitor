# src/arb/binance_adapter.py

import logging
import requests
from binance.client import Client
import os

from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())

logger = logging.getLogger('blockchain_monitor.binance')

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# Trading fee: 0.1% = 0.001
BINANCE_TRADING_FEE = 0.001

# REST API base URL
BINANCE_REST_URL = "https://api.binance.com/api/v3"


def make_binance_client(use_testnet: bool = False) -> Client:
    """
    Create a Binance client for spot trading.

    Uses env vars:
        BINANCE_API_KEY
        BINANCE_API_SECRET
    """
    if use_testnet:
        client = Client(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=True)
        client.API_URL = "https://testnet.binance.vision/api"
    else:
        client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
    return client


def get_price(symbol: str) -> float | None:
    """Get current price for a symbol (no auth required)."""
    try:
        resp = requests.get(f"{BINANCE_REST_URL}/ticker/price", params={"symbol": symbol}, timeout=5)
        if resp.status_code == 200:
            return float(resp.json()["price"])
    except Exception as e:
        logger.error(f"Binance price error for {symbol}: {e}")
    return None


def get_orderbook(symbol: str, limit: int = 5) -> dict | None:
    """Get orderbook for a symbol (no auth required)."""
    try:
        resp = requests.get(f"{BINANCE_REST_URL}/depth", params={"symbol": symbol, "limit": limit}, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "best_bid": float(data["bids"][0][0]),
                "best_ask": float(data["asks"][0][0]),
                "bid_qty": float(data["bids"][0][1]),
                "ask_qty": float(data["asks"][0][1]),
            }
    except Exception as e:
        logger.error(f"Binance orderbook error for {symbol}: {e}")
    return None


def binance_buy_cost_usdt(client: Client, symbol: str, qty_tokens: float) -> float:
    """
    Approximate USDT cost to buy `qty_tokens` of `symbol` on Binance, including fee.

    - Uses best ask from order book.
    - For large sizes, you may want to walk the book instead of only top level.
    """
    depth = client.get_order_book(symbol=symbol, limit=10)
    best_ask = float(depth["asks"][0][0])
    gross_cost = best_ask * qty_tokens
    fee = gross_cost * BINANCE_TRADING_FEE
    return gross_cost + fee


def binance_sell_proceeds_usdt(client: Client, symbol: str, qty_tokens: float) -> float:
    """
    Approximate USDT proceeds from selling `qty_tokens` of `symbol` on Binance, after fee.

    - Uses best bid from order book.
    """
    depth = client.get_order_book(symbol=symbol, limit=10)
    best_bid = float(depth["bids"][0][0])
    gross_proceeds = best_bid * qty_tokens
    fee = gross_proceeds * BINANCE_TRADING_FEE
    return gross_proceeds - fee
