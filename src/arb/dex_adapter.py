# src/arb/dex_adapter.py

"""
DEX adapter: uses Odos via src.tokens.token_swap.get_token_swap_quote
to quote tokens on Ethereum and Fraxtal.

On Ethereum:
    WFRAX <-> USDT

On Fraxtal:
    WFRAX_fraxtal <-> frxUSD_fraxtal (for backward compatibility)

Exports for WFRAX (Ethereum):
    dex_eth_sell_wfrax_proceeds_usdt(qty_wfrax) - Sell WFRAX, get USDT
    dex_eth_buy_wfrax_cost_usdt(qty_wfrax) - Cost to buy qty_wfrax WFRAX
    dex_eth_buy_wfrax_from_usdt(usdt_amount) - Buy WFRAX with USDT, get WFRAX amount

Exports for WFRAX (Fraxtal, backward compatibility):
    dex_fraxtal_buy_cost_stable_wfrax(qty_wfrax)
    dex_fraxtal_sell_proceeds_stable_wfrax(qty_wfrax)

All amounts returned are in *human stable units* (USDT / frxUSD_fraxtal),
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
ETH_STABLE_SYMBOL = "USDT"
# USDT address on Ethereum mainnet
ETH_STABLE_ADDRESS = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

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
# Ethereum DEX: WFRAX <-> USDT
# =====================================================================

def dex_eth_sell_wfrax_proceeds_usdt(qty_wfrax: float) -> float:
    """
    Proceeds in USDT (Ethereum) from SELLING `qty_wfrax` WFRAX on ETH DEX.

    Direction: WFRAX -> USDT
    """
    wfrax_address = _get_address("WFRAX")

    quote = get_token_swap_quote(
        input_token="WFRAX",
        output_token=ETH_STABLE_SYMBOL,
        input_token_address=wfrax_address,
        output_token_address=ETH_STABLE_ADDRESS,
        amount=qty_wfrax,        # human WFRAX
        api="odos",
        chain_id=ETH_CHAIN_ID,
    )
    if quote is None:
        raise RuntimeError("Odos ETH quote failed for WFRAX -> USDT")

    usdt_received = quote["output_amount"]  # human USDT
    return usdt_received


def dex_eth_buy_wfrax_cost_usdt(qty_wfrax: float) -> float:
    """
    Cost in USDT (Ethereum) to BUY `qty_wfrax` WFRAX on ETH DEX.

    Direction: USDT -> WFRAX

    Uses simple approach: quote the buy direction with an estimated USDT amount
    based on the sell direction, then adjust iteratively.
    """
    wfrax_address = _get_address("WFRAX")

    # Get initial estimate via sell direction (WFRAX -> USDT)
    sell_quote = get_token_swap_quote(
        input_token="WFRAX",
        output_token=ETH_STABLE_SYMBOL,
        input_token_address=wfrax_address,
        output_token_address=ETH_STABLE_ADDRESS,
        amount=qty_wfrax,        # human WFRAX
        api="odos",
        chain_id=ETH_CHAIN_ID,
    )
    if sell_quote is None:
        raise RuntimeError("Odos ETH quote failed for WFRAX -> USDT (initial estimate)")

    usdt_estimate = sell_quote["output_amount"]  # USDT from selling qty_wfrax
    
    # Quote buy direction with estimated amount
    buy_quote = get_token_swap_quote(
        input_token=ETH_STABLE_SYMBOL,
        output_token="WFRAX",
        input_token_address=ETH_STABLE_ADDRESS,
        output_token_address=wfrax_address,
        amount=usdt_estimate,  # human USDT
        api="odos",
        chain_id=ETH_CHAIN_ID,
    )
    if buy_quote is None:
        raise RuntimeError("Odos ETH quote failed for USDT -> WFRAX (buy direction)")

    # If we got less than target, adjust proportionally
    actual_output = buy_quote["output_amount"]
    if actual_output > 0 and actual_output < qty_wfrax:
        ratio = qty_wfrax / actual_output
        adjusted_usdt = usdt_estimate * ratio
        # Re-quote with adjusted amount
        buy_quote = get_token_swap_quote(
            input_token=ETH_STABLE_SYMBOL,
            output_token="WFRAX",
            input_token_address=ETH_STABLE_ADDRESS,
            output_token_address=wfrax_address,
            amount=adjusted_usdt,
            api="odos",
            chain_id=ETH_CHAIN_ID,
        )
        if buy_quote is None:
            return adjusted_usdt  # Return estimate if quote fails
        return buy_quote["input_amount"]
    
    return buy_quote["input_amount"]


def dex_eth_buy_wfrax_from_usdt(usdt_amount: float) -> float:
    """
    How much WFRAX can be bought on ETH DEX with `usdt_amount` USDT.

    Direction: USDT -> WFRAX
    Returns: amount of WFRAX received
    """
    wfrax_address = _get_address("WFRAX")

    quote = get_token_swap_quote(
        input_token=ETH_STABLE_SYMBOL,
        output_token="WFRAX",
        input_token_address=ETH_STABLE_ADDRESS,
        output_token_address=wfrax_address,
        amount=usdt_amount,  # human USDT
        api="odos",
        chain_id=ETH_CHAIN_ID,
    )
    if quote is None:
        raise RuntimeError("Odos ETH quote failed for USDT -> WFRAX")

    return quote["output_amount"]  # human WFRAX


def dex_eth_convert_wfrax_to_fxs(qty_wfrax: float) -> float:
    """
    Convert WFRAX to FXS on ETH DEX using Odos.
    Accounts for the negative premium when swapping from WFRAX to FXS.

    Direction: WFRAX -> FXS
    Returns: amount of FXS received
    """
    wfrax_address = _get_address("WFRAX")
    fxs_address = _get_address("FXS")

    quote = get_token_swap_quote(
        input_token="WFRAX",
        output_token="FXS",
        input_token_address=wfrax_address,
        output_token_address=fxs_address,
        amount=qty_wfrax,  # human WFRAX
        api="odos",
        chain_id=ETH_CHAIN_ID,
    )
    if quote is None:
        raise RuntimeError("Odos ETH quote failed for WFRAX -> FXS")

    return quote["output_amount"]  # human FXS


# =====================================================================
# Fraxtal DEX: WFRAX_fraxtal <-> frxUSD_fraxtal
# (Keeping for backward compatibility, but not used in simplified arb)
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
    """
    wfrax_address = FRAXTAL_WFRAX_ADDRESS

    # Get initial estimate via sell direction
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
        raise RuntimeError("Odos Fraxtal quote failed for WFRAX -> frxUSD_fraxtal (initial estimate)")

    stable_estimate = sell_quote["output_amount"]  # frxUSD_fraxtal
    
    # Quote buy direction
    buy_quote = get_token_swap_quote(
        input_token=FRAXTAL_STABLE_SYMBOL,
        output_token=FRAXTAL_WFRAX_SYMBOL,
        input_token_address=FRAXTAL_STABLE_ADDRESS,
        output_token_address=wfrax_address,
        amount=stable_estimate,  # human frxUSD_fraxtal
        api="odos",
        chain_id=FRAXTAL_CHAIN_ID,
    )
    if buy_quote is None:
        raise RuntimeError("Odos Fraxtal quote failed for frxUSD_fraxtal -> WFRAX (buy direction)")

    # Adjust if needed
    actual_output = buy_quote["output_amount"]
    if actual_output > 0 and actual_output < qty_wfrax:
        ratio = qty_wfrax / actual_output
        adjusted_stable = stable_estimate * ratio
        buy_quote = get_token_swap_quote(
            input_token=FRAXTAL_STABLE_SYMBOL,
            output_token=FRAXTAL_WFRAX_SYMBOL,
            input_token_address=FRAXTAL_STABLE_ADDRESS,
            output_token_address=wfrax_address,
            amount=adjusted_stable,
            api="odos",
            chain_id=FRAXTAL_CHAIN_ID,
        )
        if buy_quote is None:
            return adjusted_stable
        return buy_quote["input_amount"]
    
    return buy_quote["input_amount"]
