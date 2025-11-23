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
    dex_eth_sell_wfrax_proceeds_usdt,
    dex_eth_buy_wfrax_from_usdt,
    dex_eth_convert_wfrax_to_fxs,
)

from src.notifiers.telegram import TelegramNotifier  # adjust import if needed


@dataclass
class ArbScenario:
    description: str
    profit_usdt_equiv: float
    leg1: str
    leg2: str

def find_arb_for_qty(
    qty_fxs: float,
    usdt_amount: float,
    binance_symbol: str,
    use_testnet: bool = False,
) -> List[ArbScenario]:
    """
    Compare WFRAX (DEX) vs FXS (Binance) prices.

    Two scenarios:
    1. Sell fixed qty_fxs WFRAX on DEX, buy qty_fxs FXS on Binance
       - Profit = (USDT received from Binance) - (USDT received from DEX)
    
    2. Spend fixed usdt_amount to buy WFRAX on DEX, then sell that WFRAX on Binance
       - Note: This compares WFRAX on DEX vs FXS on Binance (different tokens)
       - Profit = (USDT received from Binance for FXS) - usdt_amount

    Profits are in USDT units.
    """
    client = make_binance_client(use_testnet=use_testnet)

    scenarios: List[ArbScenario] = []

    # ===== Scenario 1: Fixed quantity =====
    # Sell qty_fxs WFRAX on DEX, buy qty_fxs FXS on Binance
    dex_sell_proceeds = dex_eth_sell_wfrax_proceeds_usdt(qty_fxs)  # USDT received from DEX
    binance_buy_cost = binance_buy_cost_usdt(client, binance_symbol, qty_fxs)  # USDT spent on Binance
    
    # Profit: if we sell WFRAX on DEX and buy FXS on Binance
    # Note: Comparing WFRAX (DEX) vs FXS (Binance) - treating as equivalent for comparison
    profit1 = dex_sell_proceeds - binance_buy_cost
    scenarios.append(
        ArbScenario(
            description="Sell WFRAX on DEX, buy FXS on Binance (fixed quantity)",
            profit_usdt_equiv=profit1,
            leg1=f"SELL {qty_fxs} WFRAX on ETH DEX for ~{dex_sell_proceeds:.4f} USDT",
            leg2=f"BUY {qty_fxs} FXS on Binance ({binance_symbol}) for ~{binance_buy_cost:.4f} USDT",
        )
    )

    # ===== Scenario 2: Fixed USDT amount =====
    # Spend usdt_amount to buy WFRAX on DEX, convert to FXS, then sell FXS on Binance
    wfrax_bought_on_dex = dex_eth_buy_wfrax_from_usdt(usdt_amount)  # WFRAX received from DEX
    # Convert WFRAX to FXS (accounts for negative premium)
    fxs_from_wfrax = dex_eth_convert_wfrax_to_fxs(wfrax_bought_on_dex)  # FXS received after conversion
    # Sell FXS on Binance
    binance_sell_proceeds = binance_sell_proceeds_usdt(client, binance_symbol, fxs_from_wfrax)  # USDT received
    
    profit2 = binance_sell_proceeds - usdt_amount
    scenarios.append(
        ArbScenario(
            description="Buy WFRAX on DEX with USDT, convert to FXS, sell FXS on Binance (fixed USDT amount)",
            profit_usdt_equiv=profit2,
            leg1=f"BUY ~{wfrax_bought_on_dex:.4f} WFRAX on ETH DEX for ~{usdt_amount:.4f} USDT, convert to ~{fxs_from_wfrax:.4f} FXS",
            leg2=f"SELL ~{fxs_from_wfrax:.4f} FXS on Binance ({binance_symbol}) for ~{binance_sell_proceeds:.4f} USDT",
        )
    )

    # Sort scenarios by profit, low -> high
    scenarios.sort(key=lambda s: s.profit_usdt_equiv)

    return scenarios


def pretty_print_scenarios(scenarios: List[ArbScenario], min_profit: float = 0.0):
    print("=== Arbitrage Scenarios (sorted by profit, low -> high) ===")
    for s in scenarios:
        mark = ">>>" if s.profit_usdt_equiv > min_profit else "   "
        print(f"{mark} {s.description}")
        print(f"    Profit: {s.profit_usdt_equiv:.6f} USDT-equivalent")
        print(f"    Leg1:   {s.leg1}")
        print(f"    Leg2:   {s.leg2}")
        print()

def send_arb_alerts(
    scenarios: List[ArbScenario],
    min_profit: float,
    notifier: TelegramNotifier,
    binance_symbol: str,
    qty_fxs: float,
    usdt_amount: float,
):
    for s in scenarios:
        if s.profit_usdt_equiv <= min_profit:
            continue

        msg = (
            f"*Arb Opportunity Detected*\n\n"
            f"*Binance Market:* `{binance_symbol}`\n"
            f"*Fixed FXS Quantity:* `{qty_fxs}` tokens\n"
            f"*Fixed USDT Amount:* `{usdt_amount}` USDT\n"
            f"*Scenario:* {s.description}\n\n"
            f"*Estimated Profit:* `{s.profit_usdt_equiv:.6f} USDT-equivalent`\n\n"
            f"*Leg 1:*\n"
            f"`{s.leg1}`\n\n"
            f"*Leg 2:*\n"
            f"`{s.leg2}`\n"
        )

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


if __name__ == "__main__":
    BINANCE_SYMBOL = "FXSUSDT"
    QTY_FXS = 2000.0      # Fixed FXS quantity for scenario 1
    USDT_AMOUNT = 2000.0  # Fixed USDT amount for scenario 2

    # MIN_PROFIT_ALERT = 10.0  # USDT-equivalent
    MIN_PROFIT_ALERT = -10.0  # USDT-equivalent

    scenarios = find_arb_for_qty(
        qty_fxs=QTY_FXS,
        usdt_amount=USDT_AMOUNT,
        binance_symbol=BINANCE_SYMBOL,
        use_testnet=False,
    )
    pretty_print_scenarios(scenarios, min_profit=MIN_PROFIT_ALERT)

    notifier = _make_telegram_notifier_from_env()
    if notifier:
        send_arb_alerts(
            scenarios,
            min_profit=MIN_PROFIT_ALERT,
            notifier=notifier,
            binance_symbol=BINANCE_SYMBOL,
            qty_fxs=QTY_FXS,
            usdt_amount=USDT_AMOUNT,
        )
    else:
        print("Telegram notifier not configured; skipping alerts.")

