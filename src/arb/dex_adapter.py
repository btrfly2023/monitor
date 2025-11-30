# src/arb/dex_adapter.py

"""
DEX adapter: uses Odos via src.tokens.token_swap.get_token_swap_quote
to quote tokens on multiple chains (Ethereum, Fraxtal, etc.).

Exports generic helpers that work across chains:
    dex_sell_token_for_stable() - Sell any token for stable on any chain
    dex_buy_token_from_stable() - Buy any token with stable on any chain
    dex_convert_token_to_token() - Convert any token to any token on any chain

Exports for WFRAX (Ethereum, backward compatibility):
    dex_eth_sell_wfrax_proceeds_usdt(qty_wfrax) - Sell WFRAX, get USDT
    dex_eth_buy_wfrax_cost_usdt(qty_wfrax) - Cost to buy qty_wfrax WFRAX
    dex_eth_buy_wfrax_from_usdt(usdt_amount) - Buy WFRAX with USDT, get WFRAX amount
    dex_eth_convert_wfrax_to_fxs(qty_wfrax) - Convert WFRAX to FXS

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


#######################################################################
# Generic multi-chain DEX helpers
#######################################################################

def dex_sell_token_for_stable(
    input_token_symbol: str,
    stable_symbol: str,
    qty_input: float,
    chain_id: int = ETH_CHAIN_ID,
) -> float:
    """
    Proceeds in `stable_symbol` from selling `qty_input` of `input_token_symbol`
    on any DEX chain.

    Example: input_token_symbol='WFRAX', stable_symbol='USDT', chain_id=1
    Direction: input_token -> stable
    """
    input_addr = _get_address(input_token_symbol)
    stable_addr = _get_address(stable_symbol)

    quote = get_token_swap_quote(
        input_token=input_token_symbol,
        output_token=stable_symbol,
        input_token_address=input_addr,
        output_token_address=stable_addr,
        amount=qty_input,
        api="odos",
        chain_id=chain_id,
    )
    if quote is None:
        raise RuntimeError(
            f"Odos quote failed for {input_token_symbol} -> {stable_symbol} on chain {chain_id}"
        )

    return quote["output_amount"]


def dex_buy_token_from_stable(
    token_symbol: str,
    stable_symbol: str,
    stable_amount: float,
    chain_id: int = ETH_CHAIN_ID,
) -> float:
    """
    How much `token_symbol` can be bought with `stable_amount` of `stable_symbol`
    on any DEX chain.

    Example: token_symbol='WFRAX', stable_symbol='USDT', chain_id=1
    Direction: stable -> token
    """
    token_addr = _get_address(token_symbol)
    stable_addr = _get_address(stable_symbol)

    quote = get_token_swap_quote(
        input_token=stable_symbol,
        output_token=token_symbol,
        input_token_address=stable_addr,
        output_token_address=token_addr,
        amount=stable_amount,
        api="odos",
        chain_id=chain_id,
    )
    if quote is None:
        raise RuntimeError(
            f"Odos quote failed for {stable_symbol} -> {token_symbol} on chain {chain_id}"
        )

    return quote["output_amount"]


def dex_convert_token_to_token(
    input_token_symbol: str,
    output_token_symbol: str,
    qty_input: float,
    chain_id: int = ETH_CHAIN_ID,
) -> float:
    """
    Swap any token to any token on any DEX chain via Odos; returns output token amount.

    Example: WFRAX -> FXS on Ethereum (chain_id=1)
    Direction: input_token -> output_token
    """
    input_addr = _get_address(input_token_symbol)
    output_addr = _get_address(output_token_symbol)

    quote = get_token_swap_quote(
        input_token=input_token_symbol,
        output_token=output_token_symbol,
        input_token_address=input_addr,
        output_token_address=output_addr,
        amount=qty_input,
        api="odos",
        chain_id=chain_id,
    )
    if quote is None:
        raise RuntimeError(
            f"Odos quote failed for {input_token_symbol} -> {output_token_symbol} on chain {chain_id}"
        )

    return quote["output_amount"]


#######################################################################
# Ethereum DEX helpers (backward compatibility wrappers)
#######################################################################

def dex_eth_sell_token_for_stable(
    input_token_symbol: str,
    stable_symbol: str,
    qty_input: float,
) -> float:
    """
    Ethereum-specific wrapper for backward compatibility.
    """
    return dex_sell_token_for_stable(
        input_token_symbol=input_token_symbol,
        stable_symbol=stable_symbol,
        qty_input=qty_input,
        chain_id=ETH_CHAIN_ID,
    )


def dex_eth_buy_token_from_stable(
    token_symbol: str,
    stable_symbol: str,
    stable_amount: float,
) -> float:
    """
    Ethereum-specific wrapper for backward compatibility.
    """
    return dex_buy_token_from_stable(
        token_symbol=token_symbol,
        stable_symbol=stable_symbol,
        stable_amount=stable_amount,
        chain_id=ETH_CHAIN_ID,
    )


def dex_eth_convert_token_to_token(
    input_token_symbol: str,
    output_token_symbol: str,
    qty_input: float,
) -> float:
    """
    Ethereum-specific wrapper for backward compatibility.
    """
    return dex_convert_token_to_token(
        input_token_symbol=input_token_symbol,
        output_token_symbol=output_token_symbol,
        qty_input=qty_input,
        chain_id=ETH_CHAIN_ID,
    )


#######################################################################
# WFRAX-specific helpers (backward compatibility)
#######################################################################

def dex_eth_sell_wfrax_proceeds_usdt(qty_wfrax: float) -> float:
    """
    Proceeds in USDT (Ethereum) from SELLING `qty_wfrax` WFRAX on ETH DEX.

    Direction: WFRAX -> USDT
    (Backward compatibility wrapper)
    """
    return dex_eth_sell_token_for_stable("WFRAX", ETH_STABLE_SYMBOL, qty_wfrax)


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
    (Backward compatibility wrapper)
    """
    return dex_eth_buy_token_from_stable("WFRAX", ETH_STABLE_SYMBOL, usdt_amount)


def dex_eth_convert_wfrax_to_fxs(qty_wfrax: float) -> float:
    """
    Convert WFRAX to FXS on ETH DEX using Odos.
    Accounts for the negative premium when swapping from WFRAX to FXS.

    Direction: WFRAX -> FXS
    Returns: amount of FXS received
    (Backward compatibility wrapper)
    """
    return dex_eth_convert_token_to_token("WFRAX", "FXS", qty_wfrax)


# =====================================================================
# Fraxtal DEX: WFRAX_fraxtal <-> frxUSD_fraxtal
# (Keeping for backward compatibility, but not used in simplified arb)
# =====================================================================

def dex_fraxtal_sell_proceeds_stable_wfrax(qty_wfrax: float) -> float:
    """
    Proceeds in frxUSD_fraxtal from SELLING `qty_wfrax` WFRAX_fraxtal on Fraxtal DEX.

    Direction: WFRAX_fraxtal -> frxUSD_fraxtal
    """
    return dex_sell_token_for_stable(
        input_token_symbol=FRAXTAL_WFRAX_SYMBOL,
        stable_symbol=FRAXTAL_STABLE_SYMBOL,
        qty_input=qty_wfrax,
        chain_id=FRAXTAL_CHAIN_ID,
    )


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
