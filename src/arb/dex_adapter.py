# src/arb/dex_adapter.py

"""
DEX adapter: uses Odos via src.tokens.token_swap.get_token_swap_quote
to quote FRAX-based stables on Ethereum and Fraxtal.

On Ethereum:
    WFRAX <-> frxUSD

On Fraxtal:
    WFRAX_fraxtal <-> frxUSD_fraxtal

Exports:
    dex_eth_buy_cost_stable_fx(qty_fxs)
    dex_eth_sell_proceeds_stable_fx(qty_fxs)
    dex_fraxtal_buy_cost_stable_wfrax(qty_wfrax)
    dex_fraxtal_sell_proceeds_stable_wfrax(qty_wfrax)

All amounts returned are in *human stable units* (frxUSD / frxUSD_fraxtal),
treated as USDT-equivalent.

Note:
    - BUY legs use stable -> token direction.
    - SELL legs use token -> stable direction.
"""

from src.tokens.token_swap import (
    get_token_swap_quote,
    TOKEN_ADDRESSES,
)


# ===== Ethereum mainnet config =====
ETH_CHAIN_ID = 1
ETH_STABLE_SYMBOL = "frxUSD"
ETH_STABLE_ADDRESS = TOKEN_ADDRESSES["frxUSD"]

# ===== Fraxtal config =====
FRAXTAL_CHAIN_ID = 252  # TODO: confirm Odos chainId for Fraxtal
FRAXTAL_WFRAX_SYMBOL = "WFRAX_fraxtal"
FRAXTAL_WFRAX_ADDRESS = TOKEN_ADDRESSES["WFRAX_fraxtal"]
FRAXTAL_STABLE_SYMBOL = "frxUSD_fraxtal"
FRAXTAL_STABLE_ADDRESS = TOKEN_ADDRESSES["frxUSD_fraxtal"]


def _get_address(symbol: str) -> str:
    if symbol in TOKEN_ADDRESSES:
        return TOKEN_ADDRESSES[symbol]
    raise ValueError(f"Token symbol {symbol} not in TOKEN_ADDRESSES")


# =====================================================================
# Ethereum DEX: WFRAX <-> frxUSD
# =====================================================================

def dex_eth_sell_proceeds_stable_fx(token_symbol: str, qty_tokens: float) -> float:
    """
    Proceeds in frxUSD (Ethereum) from SELLING `qty_tokens` WFRAX on ETH DEX.

    Direction: WFRAX -> frxUSD
    """
    if token_symbol != "WFRAX":
        raise ValueError("dex_eth_sell_proceeds_stable_fx currently expects token_symbol == 'WFRAX'")

    wfrax_address = _get_address("WFRAX")

    quote = get_token_swap_quote(
        input_token="WFRAX",
        output_token=ETH_STABLE_SYMBOL,
        input_token_address=wfrax_address,
        output_token_address=ETH_STABLE_ADDRESS,
        amount=qty_tokens,        # human WFRAX
        api="odos",
        chain_id=ETH_CHAIN_ID,
    )
    if quote is None:
        raise RuntimeError("Odos ETH quote failed for WFRAX -> frxUSD")

    stable_received = quote["output_amount"]  # human frxUSD
    return stable_received


def dex_eth_buy_cost_stable_fx(token_symbol: str, qty_tokens: float) -> float:
    """
    Cost in frxUSD (Ethereum) to BUY `qty_tokens` of WFRAX on ETH DEX.

    Direction: frxUSD -> WFRAX

    Implementation (simple but directional):
        1) Quote WFRAX -> frxUSD for qty_tokens (to get a mid price).
        2) Use that mid price as an approximate frxUSD input size.
        3) Quote frxUSD -> WFRAX with that input size.
        4) Return the actual frxUSD spent according to the buy-direction quote.

    This captures spread/asymmetry between buy and sell directions,
    even though the size is matched only approximately.
    """
    if token_symbol != "WFRAX":
        raise ValueError("dex_eth_buy_cost_stable_fx currently expects token_symbol == 'WFRAX'")

    wfrax_address = _get_address("WFRAX")

    # Step 1: mid price via sell direction (WFRAX -> frxUSD)
    sell_quote = get_token_swap_quote(
        input_token="WFRAX",
        output_token=ETH_STABLE_SYMBOL,
        input_token_address=wfrax_address,
        output_token_address=ETH_STABLE_ADDRESS,
        amount=qty_tokens,        # human WFRAX
        api="odos",
        chain_id=ETH_CHAIN_ID,
    )
    if sell_quote is None:
        raise RuntimeError(
            "Odos ETH quote failed for WFRAX -> frxUSD (mid-price for buy approximation)"
        )

    stable_mid = sell_quote["output_amount"]  # frxUSD from selling qty_tokens
    approx_stable_in = stable_mid

    # Step 2: actual buy direction (frxUSD -> WFRAX)
    buy_quote = get_token_swap_quote(
        input_token=ETH_STABLE_SYMBOL,
        output_token="WFRAX",
        input_token_address=ETH_STABLE_ADDRESS,
        output_token_address=wfrax_address,
        amount=approx_stable_in,  # human frxUSD
        api="odos",
        chain_id=ETH_CHAIN_ID,
    )
    if buy_quote is None:
        raise RuntimeError("Odos ETH quote failed for frxUSD -> WFRAX (buy direction)")

    # The quote structure was normalized in get_token_swap_quote.
    # We want the actual frxUSD input used for this route.
    stable_spent = buy_quote["input_amount"]  # human frxUSD
    return stable_spent


# =====================================================================
# Fraxtal DEX: WFRAX_fraxtal <-> frxUSD_fraxtal
# =====================================================================

def dex_fraxtal_sell_proceeds_stable_wfrax(qty_wfrax: float) -> float:
    """
    Proceeds in frxUSD_fraxtal from SELLING `qty_wfrax` WFRAX_fraxtal on Fraxtal DEX.

    Direction: WFRAX_fraxtal -> frxUSD_fraxtal
    """
    wfrax_address = FRAXTAL_WFRAX_ADDRESS

    quote = get_token_swap_quote(
        input_token=FRAXTAL_WFRAX_SYMBOL,
        output_token=FRAXTAL_STABLE_SYMBOL,
        input_token_address=wfrax_address,
        output_token_address=FRAXTAL_STABLE_ADDRESS,
        amount=qty_wfrax,         # human WFRAX
        api="odos",
        chain_id=FRAXTAL_CHAIN_ID,
    )
    if quote is None:
        raise RuntimeError("Odos Fraxtal quote failed for WFRAX -> frxUSD_fraxtal")

    stable_received = quote["output_amount"]  # human frxUSD_fraxtal
    return stable_received


def dex_fraxtal_buy_cost_stable_wfrax(qty_wfrax: float) -> float:
    """
    Cost in frxUSD_fraxtal to BUY `qty_wfrax` WFRAX_fraxtal on Fraxtal DEX.

    Direction: frxUSD_fraxtal -> WFRAX_fraxtal

    Implementation mirrors the ETH version:
        1) Quote WFRAX -> frxUSD_fraxtal for qty_wfrax (mid price).
        2) Use that to approximate needed frxUSD_fraxtal input.
        3) Quote frxUSD_fraxtal -> WFRAX with that input.
        4) Return the actual stable spent.
    """
    wfrax_address = FRAXTAL_WFRAX_ADDRESS

    # Step 1: mid price via sell direction (WFRAX -> frxUSD_fraxtal)
    sell_quote = get_token_swap_quote(
        input_token=FRAXTAL_WFRAX_SYMBOL,
        output_token=FRAXTAL_STABLE_SYMBOL,
        input_token_address=wfrax_address,
        output_token_address=FRAXTAL_STABLE_ADDRESS,
        amount=qty_wfrax,         # human WFRAX
        api="odos",
        chain_id=FRAXTAL_CHAIN_ID,
    )
    if sell_quote is None:
        raise RuntimeError(
            "Odos Fraxtal quote failed for WFRAX -> frxUSD_fraxtal (mid-price for buy approximation)"
        )

    stable_mid = sell_quote["output_amount"]  # frxUSD_fraxtal
    approx_stable_in = stable_mid

    # Step 2: actual buy direction (frxUSD_fraxtal -> WFRAX)
    buy_quote = get_token_swap_quote(
        input_token=FRAXTAL_STABLE_SYMBOL,
        output_token=FRAXTAL_WFRAX_SYMBOL,
        input_token_address=FRAXTAL_STABLE_ADDRESS,
        output_token_address=wfrax_address,
        amount=approx_stable_in,  # human frxUSD_fraxtal
        api="odos",
        chain_id=FRAXTAL_CHAIN_ID,
    )
    if buy_quote is None:
        raise RuntimeError(
            "Odos Fraxtal quote failed for frxUSD_fraxtal -> WFRAX (buy direction)"
        )

    stable_spent = buy_quote["input_amount"]  # human frxUSD_fraxtal
    return stable_spent
