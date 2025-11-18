# src/arb/binance_adapter.py

from binance.client import Client
import os

from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())


BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# Trading fee: 0.1% = 0.001
BINANCE_TRADING_FEE = 0.001


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
