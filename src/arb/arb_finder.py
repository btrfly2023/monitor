# src/arb/arb_finder.py

from dataclasses import dataclass
from typing import List, Optional
import os

from .binance_adapter import (
    make_binance_client,
    binance_buy_cost_usdt,
    binance_sell_proceeds_usdt,
)
from .dex_adapter import (
    dex_eth_sell_token_for_stable,
    dex_eth_buy_token_from_stable,
    dex_eth_convert_token_to_token,
    dex_sell_token_for_stable,
    dex_buy_token_from_stable,
    dex_convert_token_to_token,
)

from src.notifiers.telegram import TelegramNotifier  # adjust import if needed


@dataclass
class ArbScenario:
    description: str
    profit_usdt_equiv: float
    leg1: str
    leg2: Optional[str] = None
    leg3: Optional[str] = None


@dataclass
class ArbConfig:
    """
    Generic arb configuration supporting:
    1. CEX-DEX arbitrage (Binance <-> Ethereum DEX)
    2. DEX-DEX arbitrage (Ethereum DEX <-> Another chain DEX)

    For CEX-DEX:
        venue1_type='cex'
        venue1_symbol='FXSUSDT'
        venue1_token_symbol='FXS'
        venue2_type='dex'
        venue2_chain_id=1
        venue2_token_symbol='WFRAX'
        venue2_stable_symbol='USDT'

    For DEX-DEX (cross-chain):
        venue1_type='dex'
        venue1_chain_id=1
        venue1_token_symbol='frxETH'
        venue1_stable_symbol='frxUSD'
        venue2_type='dex'
        venue2_chain_id=252
        venue2_token_symbol='frxETH_fraxtal'
        venue2_stable_symbol='frxUSD_fraxtal'
    """
    # Required fields (no defaults)
    venue1_type: str  # 'cex' or 'dex'
    venue1_token_symbol: str
    venue2_type: str  # 'cex' or 'dex'
    venue2_token_symbol: str

    # Optional fields (with defaults)
    venue1_symbol: Optional[str] = None  # For CEX: trading pair like 'FXSUSDT'
    venue1_chain_id: Optional[int] = None  # For DEX: chain ID
    venue1_stable_symbol: Optional[str] = None  # For DEX: stable coin symbol
    venue2_symbol: Optional[str] = None  # For CEX: trading pair
    venue2_chain_id: Optional[int] = None  # For DEX: chain ID
    venue2_stable_symbol: Optional[str] = None  # For DEX: stable coin symbol
    description_prefix: str = ""
    use_testnet: bool = False


def _is_cross_chain_dex_dex(config: ArbConfig) -> bool:
    """Check if this is a cross-chain DEX-DEX arbitrage"""
    return (
        config.venue1_type == 'dex' and 
        config.venue2_type == 'dex' and 
        config.venue1_chain_id != config.venue2_chain_id
    )


def _needs_token_conversion(config: ArbConfig) -> bool:
    """
    Check if we need token conversion (not just cross-chain bridging).

    For cross-chain DEX-DEX:
    - frxETH (ETH) → frxETH_fraxtal (Fraxtal): Different tokens, need conversion
    - frxUSD (ETH) → frxUSD_fraxtal (Fraxtal): Same token, just bridging

    For CEX-DEX:
    - FXS (Binance) → WFRAX (DEX): Different tokens, need conversion
    """
    # Strip chain suffixes to check if base tokens are the same
    token1_base = config.venue1_token_symbol.split('_')[0]
    token2_base = config.venue2_token_symbol.split('_')[0]

    return token1_base != token2_base


def find_arb_for_qty(
    qty_token: float,
    usdt_amount: float,
    config: ArbConfig,
) -> List[ArbScenario]:
    """
    Generic arb finder supporting CEX-DEX and DEX-DEX arbitrage.

    Two scenarios:
    1. Fixed token quantity: sell on venue1, buy on venue2 (with conversion if needed).
    2. Fixed USDT amount: buy on venue1, sell on venue2 (with conversion if needed).
    """
    scenarios: List[ArbScenario] = []
    prefix = f"[{config.description_prefix}] " if config.description_prefix else ""

    is_cross_chain = _is_cross_chain_dex_dex(config)
    needs_conversion = _needs_token_conversion(config)

    # ===== Scenario 1: Fixed quantity =====
    # Sell qty_token on venue1, convert if needed, buy on venue2

    # Sell on venue1
    if config.venue1_type == 'cex':
        client = make_binance_client(use_testnet=config.use_testnet)
        venue1_sell_proceeds = binance_sell_proceeds_usdt(
            client, 
            config.venue1_symbol, 
            qty_token
        )
        venue1_name = f"Binance ({config.venue1_symbol})"
    elif config.venue1_type == 'dex':
        venue1_sell_proceeds = dex_sell_token_for_stable(
            input_token_symbol=config.venue1_token_symbol,
            stable_symbol=config.venue1_stable_symbol,
            qty_input=qty_token,
            chain_id=config.venue1_chain_id,
        )
        venue1_name = f"DEX Chain-{config.venue1_chain_id}"
    else:
        raise ValueError(f"Unknown venue1_type: {config.venue1_type}")

    # Handle conversion/bridging
    conversion_leg = None
    qty_venue2_token = qty_token  # Default: same quantity
    stable_for_venue2 = venue1_sell_proceeds  # Default: same stable amount

    if is_cross_chain:
        # Cross-chain DEX-DEX: we have stable coins on both chains
        # The stable amounts should be equivalent (1:1 after bridging)
        conversion_leg = (
            f"BRIDGE ~{venue1_sell_proceeds:.4f} {config.venue1_stable_symbol} "
            f"from Chain-{config.venue1_chain_id} → "
            f"{config.venue2_stable_symbol} on Chain-{config.venue2_chain_id}"
        )
        stable_for_venue2 = venue1_sell_proceeds  # 1:1 bridging

    elif needs_conversion:
        # Same-chain token conversion (e.g., FXS → WFRAX on Ethereum)
        if config.venue2_type == 'dex':
            # Convert on venue2's DEX
            qty_venue2_token = dex_convert_token_to_token(
                input_token_symbol=config.venue1_token_symbol,
                output_token_symbol=config.venue2_token_symbol,
                qty_input=qty_token,
                chain_id=config.venue2_chain_id,
            )
            conversion_leg = (
                f"CONVERT {qty_token} {config.venue1_token_symbol} → "
                f"~{qty_venue2_token:.4f} {config.venue2_token_symbol} on DEX Chain-{config.venue2_chain_id}"
            )
        elif config.venue1_type == 'dex':
            # Convert on venue1's DEX
            qty_venue2_token = dex_convert_token_to_token(
                input_token_symbol=config.venue1_token_symbol,
                output_token_symbol=config.venue2_token_symbol,
                qty_input=qty_token,
                chain_id=config.venue1_chain_id,
            )
            conversion_leg = (
                f"CONVERT {qty_token} {config.venue1_token_symbol} → "
                f"~{qty_venue2_token:.4f} {config.venue2_token_symbol} on DEX Chain-{config.venue1_chain_id}"
            )

    # Buy on venue2
    if config.venue2_type == 'cex':
        client = make_binance_client(use_testnet=config.use_testnet)
        venue2_buy_cost = binance_buy_cost_usdt(
            client,
            config.venue2_symbol,
            qty_venue2_token
        )
        venue2_name = f"Binance ({config.venue2_symbol})"
    elif config.venue2_type == 'dex':
        # For cross-chain, we're buying with the bridged stable
        # For same-chain conversion, we already converted the token
        if is_cross_chain:
            # Buy venue2_token with stable_for_venue2
            qty_venue2_token = dex_buy_token_from_stable(
                token_symbol=config.venue2_token_symbol,
                stable_symbol=config.venue2_stable_symbol,
                stable_amount=stable_for_venue2,
                chain_id=config.venue2_chain_id,
            )
            venue2_buy_cost = stable_for_venue2
        else:
            # Estimate cost for buying qty_venue2_token
            from .dex_adapter import get_token_swap_quote, _get_address

            token_addr = _get_address(config.venue2_token_symbol)
            stable_addr = _get_address(config.venue2_stable_symbol)

            # Get sell quote for estimation
            sell_quote = get_token_swap_quote(
                input_token=config.venue2_token_symbol,
                output_token=config.venue2_stable_symbol,
                input_token_address=token_addr,
                output_token_address=stable_addr,
                amount=qty_venue2_token,
                api="odos",
                chain_id=config.venue2_chain_id,
            )
            if sell_quote is None:
                raise RuntimeError(f"Failed to get quote for {config.venue2_token_symbol}")

            stable_estimate = sell_quote["output_amount"]

            # Get buy quote
            buy_quote = get_token_swap_quote(
                input_token=config.venue2_stable_symbol,
                output_token=config.venue2_token_symbol,
                input_token_address=stable_addr,
                output_token_address=token_addr,
                amount=stable_estimate,
                api="odos",
                chain_id=config.venue2_chain_id,
            )
            if buy_quote is None:
                venue2_buy_cost = stable_estimate
            else:
                # Adjust if needed
                actual_output = buy_quote["output_amount"]
                if actual_output > 0 and actual_output < qty_venue2_token:
                    ratio = qty_venue2_token / actual_output
                    venue2_buy_cost = stable_estimate * ratio
                else:
                    venue2_buy_cost = buy_quote["input_amount"]

        venue2_name = f"DEX Chain-{config.venue2_chain_id}"
    else:
        raise ValueError(f"Unknown venue2_type: {config.venue2_type}")

    profit1 = venue1_sell_proceeds - venue2_buy_cost

    scenario_desc = (
        f"{prefix}Sell {config.venue1_token_symbol} on {venue1_name}, "
        f"{'bridge, ' if is_cross_chain else ''}"
        f"{'convert, ' if needs_conversion and not is_cross_chain else ''}"
        f"buy {config.venue2_token_symbol} on {venue2_name} (fixed quantity)"
    )

    scenarios.append(
        ArbScenario(
            description=scenario_desc,
            profit_usdt_equiv=profit1,
            leg1=(
                f"SELL {qty_token} {config.venue1_token_symbol} on {venue1_name} "
                f"for ~{venue1_sell_proceeds:.4f} {config.venue1_stable_symbol}"
            ),
            leg2=conversion_leg,
            leg3=(
                f"BUY ~{qty_venue2_token:.4f} {config.venue2_token_symbol} on {venue2_name} "
                f"for ~{venue2_buy_cost:.4f} {config.venue2_stable_symbol}"
            ),
        )
    )

    # ===== Scenario 2: Fixed USDT amount =====
    # Buy on venue1 with usdt_amount, convert/bridge if needed, sell on venue2

    # Buy on venue1
    if config.venue1_type == 'cex':
        client = make_binance_client(use_testnet=config.use_testnet)
        # For CEX, we need to calculate how much token we can buy with usdt_amount
        # Use sell quote as approximation
        temp_qty = usdt_amount / (venue1_sell_proceeds / qty_token)  # rough estimate
        venue1_buy_cost = binance_buy_cost_usdt(client, config.venue1_symbol, temp_qty)

        # Adjust to match usdt_amount
        if venue1_buy_cost > 0:
            adjusted_qty = temp_qty * (usdt_amount / venue1_buy_cost)
            venue1_tokens_bought = adjusted_qty
        else:
            venue1_tokens_bought = temp_qty
    elif config.venue1_type == 'dex':
        venue1_tokens_bought = dex_buy_token_from_stable(
            token_symbol=config.venue1_token_symbol,
            stable_symbol=config.venue1_stable_symbol,
            stable_amount=usdt_amount,
            chain_id=config.venue1_chain_id,
        )
    else:
        raise ValueError(f"Unknown venue1_type: {config.venue1_type}")

    # Sell on venue1 to get stable
    if config.venue1_type == 'cex':
        venue1_stable_amount = binance_sell_proceeds_usdt(
            client,
            config.venue1_symbol,
            venue1_tokens_bought,
        )
    elif config.venue1_type == 'dex':
        venue1_stable_amount = dex_sell_token_for_stable(
            input_token_symbol=config.venue1_token_symbol,
            stable_symbol=config.venue1_stable_symbol,
            qty_input=venue1_tokens_bought,
            chain_id=config.venue1_chain_id,
        )
    else:
        raise ValueError(f"Unknown venue1_type: {config.venue1_type}")

    # Handle conversion/bridging for scenario 2
    conversion_leg2 = None
    venue2_stable_amount = venue1_stable_amount

    if is_cross_chain:
        # Bridge stable from venue1 to venue2
        conversion_leg2 = (
            f"BRIDGE ~{venue1_stable_amount:.4f} {config.venue1_stable_symbol} "
            f"from Chain-{config.venue1_chain_id} → "
            f"{config.venue2_stable_symbol} on Chain-{config.venue2_chain_id}"
        )
        venue2_stable_amount = venue1_stable_amount  # 1:1 bridging

    # Buy on venue2 with stable
    if config.venue2_type == 'cex':
        client = make_binance_client(use_testnet=config.use_testnet)
        # Estimate how much token we can buy
        temp_qty2 = venue2_stable_amount / (venue1_sell_proceeds / qty_token)
        venue2_tokens = temp_qty2
    elif config.venue2_type == 'dex':
        venue2_tokens = dex_buy_token_from_stable(
            token_symbol=config.venue2_token_symbol,
            stable_symbol=config.venue2_stable_symbol,
            stable_amount=venue2_stable_amount,
            chain_id=config.venue2_chain_id,
        )
    else:
        raise ValueError(f"Unknown venue2_type: {config.venue2_type}")

    # Sell on venue2 to get final stable amount
    if config.venue2_type == 'cex':
        client = make_binance_client(use_testnet=config.use_testnet)
        venue2_sell_proceeds = binance_sell_proceeds_usdt(
            client,
            config.venue2_symbol,
            venue2_tokens,
        )
    elif config.venue2_type == 'dex':
        venue2_sell_proceeds = dex_sell_token_for_stable(
            input_token_symbol=config.venue2_token_symbol,
            stable_symbol=config.venue2_stable_symbol,
            qty_input=venue2_tokens,
            chain_id=config.venue2_chain_id,
        )
    else:
        raise ValueError(f"Unknown venue2_type: {config.venue2_type}")

    profit2 = venue2_sell_proceeds - usdt_amount

    scenario2_desc = (
        f"{prefix}Buy {config.venue1_token_symbol} on {venue1_name}, sell for stable, "
        f"{'bridge, ' if is_cross_chain else ''}"
        f"buy {config.venue2_token_symbol} on {venue2_name}, sell (round-trip)"
    )

    scenarios.append(
        ArbScenario(
            description=scenario2_desc,
            profit_usdt_equiv=profit2,
            leg1=(
                f"BUY ~{venue1_tokens_bought:.4f} {config.venue1_token_symbol} on {venue1_name} "
                f"for ~{usdt_amount:.4f} {config.venue1_stable_symbol}, "
                f"SELL for ~{venue1_stable_amount:.4f} {config.venue1_stable_symbol}"
            ),
            leg2=conversion_leg2,
            leg3=(
                f"BUY ~{venue2_tokens:.4f} {config.venue2_token_symbol} on {venue2_name}, "
                f"SELL for ~{venue2_sell_proceeds:.4f} {config.venue2_stable_symbol}"
            ),
        )
    )

    scenarios.sort(key=lambda s: s.profit_usdt_equiv)
    return scenarios


def pretty_print_scenarios(scenarios: List[ArbScenario], min_profit: float = 0.0):
    print("=== Arbitrage Scenarios (sorted by profit, low -> high) ===")
    for s in scenarios:
        mark = ">>>" if s.profit_usdt_equiv > min_profit else "   "
        print(f"{mark} {s.description}")
        print(f"    Profit: {s.profit_usdt_equiv:.6f} USDT-equivalent")
        print(f"    Leg1:   {s.leg1}")
        if s.leg2:
            print(f"    Leg2:   {s.leg2}")
        if s.leg3:
            print(f"    Leg3:   {s.leg3}")
        print()


def send_arb_alerts(
    scenarios: List[ArbScenario],
    min_profit: float,
    notifier: TelegramNotifier,
    config: ArbConfig,
    qty_token: float,
    usdt_amount: float,
):
    for s in scenarios:
        if s.profit_usdt_equiv <= min_profit:
            continue

        msg = (
            f"*Arb Opportunity Detected*\n\n"
            f"*Config:* {config.description_prefix}\n"
            f"*Fixed Token Quantity:* `{qty_token}` tokens\n"
            f"*Fixed USDT Amount:* `{usdt_amount}` USDT\n"
            f"*Scenario:* {s.description}\n\n"
            f"*Estimated Profit:* `{s.profit_usdt_equiv:.6f} USDT-equivalent`\n\n"
            f"*Leg 1:*\n"
            f"`{s.leg1}`\n\n"
        )

        if s.leg2:
            msg += f"*Leg 2:*\n`{s.leg2}`\n\n"

        if s.leg3:
            msg += f"*Leg 3:*\n`{s.leg3}`\n"

        notifier.send_message(msg, urgent=True)


def _make_telegram_notifier_from_env() -> Optional[TelegramNotifier]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return None

    second_token = os.getenv("TELEGRAM_SECOND_BOT_TOKEN")
    second_chat_id = os.getenv("TELEGRAM_SECOND_CHAT_ID")

    notifier = TelegramNotifier(
        token=token,
        chat_id=chat_id,
        second_token=second_token,
        second_chat_id=second_chat_id,
    )
    return notifier
