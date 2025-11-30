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
    dex_sell_token_for_stable,
    dex_buy_token_from_stable,
)

from src.notifiers.telegram import TelegramNotifier  # adjust import if needed


@dataclass
class ArbScenario:
    description: str
    profit_usdt: float
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


def _is_cex_dex(config: ArbConfig) -> bool:
    """Check if this is CEX-DEX arbitrage"""
    return (
        (config.venue1_type == 'cex' and config.venue2_type == 'dex') or
        (config.venue1_type == 'dex' and config.venue2_type == 'cex')
    )


def find_arb_for_qty(
    qty_token: float,  # Deprecated, kept for backward compatibility
    usdt_amount: float,
    config: ArbConfig,
) -> List[ArbScenario]:
    """
    Simplified arb finder: Always start with USDT, end with USDT.

    Two scenarios:
    1. Buy on venue1, sell on venue2 (with bridging/conversion if needed)
    2. Buy on venue2, sell on venue1 (with bridging/conversion if needed)

    Both scenarios:
    - Start with fixed USDT amount
    - End with USDT amount
    - Profit = Final USDT - Initial USDT

    Supports:
    - CEX-DEX: Buy FXS on Binance → Sell WFRAX on DEX (or reverse)
    - DEX-DEX: Buy frxETH on ETH → Bridge → Sell on Fraxtal (or reverse)
    """
    scenarios: List[ArbScenario] = []
    prefix = f"[{config.description_prefix}] " if config.description_prefix else ""

    is_cross_chain = _is_cross_chain_dex_dex(config)
    is_cex_dex = _is_cex_dex(config)

    # Get venue names for display
    if config.venue1_type == 'cex':
        venue1_name = f"Binance ({config.venue1_symbol})"
    else:
        venue1_name = f"DEX Chain-{config.venue1_chain_id}"

    if config.venue2_type == 'cex':
        venue2_name = f"Binance ({config.venue2_symbol})"
    else:
        venue2_name = f"DEX Chain-{config.venue2_chain_id}"

    # ===== Scenario 1: Buy on venue1, sell on venue2 =====
    # CEX-DEX: Buy FXS on Binance → Sell WFRAX on DEX
    # DEX-DEX: Buy frxETH on ETH → Bridge → Sell on Fraxtal

    try:
        # Step 1: Buy token on venue1 with usdt_amount
        if config.venue1_type == 'cex':
            client = make_binance_client(use_testnet=config.use_testnet)
            # For CEX, we need to estimate how much token we can buy
            # Get current price by doing a test sell
            test_qty = 1.0
            test_proceeds = binance_sell_proceeds_usdt(client, config.venue1_symbol, test_qty)
            if test_proceeds > 0:
                price_per_token = test_proceeds / test_qty
                estimated_qty = usdt_amount / price_per_token
            else:
                estimated_qty = usdt_amount / 100  # Fallback estimate

            venue1_tokens_bought = estimated_qty
            venue1_cost = usdt_amount
        elif config.venue1_type == 'dex':
            venue1_tokens_bought = dex_buy_token_from_stable(
                token_symbol=config.venue1_token_symbol,
                stable_symbol=config.venue1_stable_symbol,
                stable_amount=usdt_amount,
                chain_id=config.venue1_chain_id,
            )
            venue1_cost = usdt_amount
        else:
            raise ValueError(f"Unknown venue1_type: {config.venue1_type}")

        # Step 2: Handle conversion/bridging
        conversion_leg = None
        venue2_tokens_to_sell = venue1_tokens_bought

        if is_cex_dex:
            # CEX-DEX: Need to convert tokens (e.g., FXS → WFRAX)
            # For CEX → DEX: Buy FXS on Binance, convert to WFRAX on DEX
            if config.venue1_type == 'cex':
                # Convert venue1_token to venue2_token on DEX
                from .dex_adapter import dex_convert_token_to_token
                venue2_tokens_to_sell = dex_convert_token_to_token(
                    input_token_symbol=config.venue1_token_symbol,
                    output_token_symbol=config.venue2_token_symbol,
                    qty_input=venue1_tokens_bought,
                    chain_id=config.venue2_chain_id,
                )
                conversion_leg = (
                    f"CONVERT ~{venue1_tokens_bought:.6f} {config.venue1_token_symbol} → "
                    f"~{venue2_tokens_to_sell:.6f} {config.venue2_token_symbol} on DEX Chain-{config.venue2_chain_id}"
                )
            # For DEX → CEX: No conversion needed, tokens are the same

        elif is_cross_chain:
            # DEX-DEX cross-chain: Bridge the token
            conversion_leg = (
                f"BRIDGE ~{venue1_tokens_bought:.6f} {config.venue1_token_symbol} "
                f"from Chain-{config.venue1_chain_id} → "
                f"{config.venue2_token_symbol} on Chain-{config.venue2_chain_id}"
            )
            venue2_tokens_to_sell = venue1_tokens_bought  # Assume 1:1 bridging

        # Step 3: Sell token on venue2
        if config.venue2_type == 'cex':
            client = make_binance_client(use_testnet=config.use_testnet)
            venue2_proceeds = binance_sell_proceeds_usdt(
                client,
                config.venue2_symbol,
                venue2_tokens_to_sell,
            )
        elif config.venue2_type == 'dex':
            venue2_proceeds = dex_sell_token_for_stable(
                input_token_symbol=config.venue2_token_symbol,
                stable_symbol=config.venue2_stable_symbol,
                qty_input=venue2_tokens_to_sell,
                chain_id=config.venue2_chain_id,
            )
        else:
            raise ValueError(f"Unknown venue2_type: {config.venue2_type}")

        profit1 = venue2_proceeds - usdt_amount

        scenario1_desc = (
            f"{prefix}Buy {config.venue1_token_symbol} on {venue1_name}, "
            f"{'convert, ' if is_cex_dex and config.venue1_type == 'cex' else ''}"
            f"{'bridge, ' if is_cross_chain else ''}"
            f"sell {config.venue2_token_symbol} on {venue2_name}"
        )

        scenarios.append(
            ArbScenario(
                description=scenario1_desc,
                profit_usdt=profit1,
                leg1=(
                    f"BUY ~{venue1_tokens_bought:.6f} {config.venue1_token_symbol} on {venue1_name} "
                    f"for {usdt_amount:.2f} {config.venue1_stable_symbol or 'USDT'}"
                ),
                leg2=conversion_leg,
                leg3=(
                    f"SELL ~{venue2_tokens_to_sell:.6f} {config.venue2_token_symbol} on {venue2_name} "
                    f"for ~{venue2_proceeds:.2f} {config.venue2_stable_symbol or 'USDT'}"
                ),
            )
        )
    except Exception as e:
        print(f"Error in scenario 1: {e}")
        import traceback
        traceback.print_exc()

    # ===== Scenario 2: Buy on venue2, sell on venue1 =====
    # CEX-DEX: Buy WFRAX on DEX → Sell FXS on Binance
    # DEX-DEX: Buy frxETH on Fraxtal → Bridge → Sell on ETH

    try:
        # Step 1: Buy token on venue2 with usdt_amount
        if config.venue2_type == 'cex':
            client = make_binance_client(use_testnet=config.use_testnet)
            # Estimate how much token we can buy
            test_qty = 1.0
            test_proceeds = binance_sell_proceeds_usdt(client, config.venue2_symbol, test_qty)
            if test_proceeds > 0:
                price_per_token = test_proceeds / test_qty
                estimated_qty = usdt_amount / price_per_token
            else:
                estimated_qty = usdt_amount / 100

            venue2_tokens_bought = estimated_qty
            venue2_cost = usdt_amount
        elif config.venue2_type == 'dex':
            venue2_tokens_bought = dex_buy_token_from_stable(
                token_symbol=config.venue2_token_symbol,
                stable_symbol=config.venue2_stable_symbol,
                stable_amount=usdt_amount,
                chain_id=config.venue2_chain_id,
            )
            venue2_cost = usdt_amount
        else:
            raise ValueError(f"Unknown venue2_type: {config.venue2_type}")

        # Step 2: Handle conversion/bridging
        conversion_leg2 = None
        venue1_tokens_to_sell = venue2_tokens_bought

        if is_cex_dex:
            # CEX-DEX: Need to convert tokens
            # For DEX → CEX: Buy WFRAX on DEX, convert to FXS on DEX
            if config.venue2_type == 'cex':
                # No conversion needed, tokens are the same
                pass
            else:
                # Convert venue2_token to venue1_token on DEX
                from .dex_adapter import dex_convert_token_to_token
                venue1_tokens_to_sell = dex_convert_token_to_token(
                    input_token_symbol=config.venue2_token_symbol,
                    output_token_symbol=config.venue1_token_symbol,
                    qty_input=venue2_tokens_bought,
                    chain_id=config.venue2_chain_id,
                )
                conversion_leg2 = (
                    f"CONVERT ~{venue2_tokens_bought:.6f} {config.venue2_token_symbol} → "
                    f"~{venue1_tokens_to_sell:.6f} {config.venue1_token_symbol} on DEX Chain-{config.venue2_chain_id}"
                )

        elif is_cross_chain:
            # DEX-DEX cross-chain: Bridge the token
            conversion_leg2 = (
                f"BRIDGE ~{venue2_tokens_bought:.6f} {config.venue2_token_symbol} "
                f"from Chain-{config.venue2_chain_id} → "
                f"{config.venue1_token_symbol} on Chain-{config.venue1_chain_id}"
            )
            venue1_tokens_to_sell = venue2_tokens_bought  # Assume 1:1 bridging

        # Step 3: Sell token on venue1
        if config.venue1_type == 'cex':
            client = make_binance_client(use_testnet=config.use_testnet)
            venue1_proceeds = binance_sell_proceeds_usdt(
                client,
                config.venue1_symbol,
                venue1_tokens_to_sell,
            )
        elif config.venue1_type == 'dex':
            venue1_proceeds = dex_sell_token_for_stable(
                input_token_symbol=config.venue1_token_symbol,
                stable_symbol=config.venue1_stable_symbol,
                qty_input=venue1_tokens_to_sell,
                chain_id=config.venue1_chain_id,
            )
        else:
            raise ValueError(f"Unknown venue1_type: {config.venue1_type}")

        profit2 = venue1_proceeds - usdt_amount

        scenario2_desc = (
            f"{prefix}Buy {config.venue2_token_symbol} on {venue2_name}, "
            f"{'convert, ' if is_cex_dex and config.venue2_type == 'dex' else ''}"
            f"{'bridge, ' if is_cross_chain else ''}"
            f"sell {config.venue1_token_symbol} on {venue1_name}"
        )

        scenarios.append(
            ArbScenario(
                description=scenario2_desc,
                profit_usdt=profit2,
                leg1=(
                    f"BUY ~{venue2_tokens_bought:.6f} {config.venue2_token_symbol} on {venue2_name} "
                    f"for {usdt_amount:.2f} {config.venue2_stable_symbol or 'USDT'}"
                ),
                leg2=conversion_leg2,
                leg3=(
                    f"SELL ~{venue1_tokens_to_sell:.6f} {config.venue1_token_symbol} on {venue1_name} "
                    f"for ~{venue1_proceeds:.2f} {config.venue1_stable_symbol or 'USDT'}"
                ),
            )
        )
    except Exception as e:
        print(f"Error in scenario 2: {e}")
        import traceback
        traceback.print_exc()

    scenarios.sort(key=lambda s: s.profit_usdt)
    return scenarios


def pretty_print_scenarios(scenarios: List[ArbScenario], min_profit: float = 0.0):
    print("=== Arbitrage Scenarios (sorted by profit, low -> high) ===")
    for s in scenarios:
        mark = ">>>" if s.profit_usdt > min_profit else "   "
        print(f"{mark} {s.description}")
        print(f"    Profit: {s.profit_usdt:.6f} USDT")
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
        if s.profit_usdt <= min_profit:
            continue

        msg = (
            f"*Arb Opportunity Detected*\n\n"
            f"*Config:* {config.description_prefix}\n"
            f"*Starting Amount:* `{usdt_amount}` USDT\n"
            f"*Scenario:* {s.description}\n\n"
            f"*Estimated Profit:* `{s.profit_usdt:.6f} USDT`\n\n"
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
