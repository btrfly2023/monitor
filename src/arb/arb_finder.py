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
    dex_eth_buy_cost_stable_fx,
    dex_eth_sell_proceeds_stable_fx,
    dex_fraxtal_buy_cost_stable_wfrax,
    dex_fraxtal_sell_proceeds_stable_wfrax,
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
    qty_wfrax: float,
    binance_symbol: str,
    use_testnet: bool = False,
) -> List[ArbScenario]:
    """
    Compare:
      - Binance FXSUSDT (FXS <-> USDT)
      - ETH DEX WFRAX <-> frxUSD
      - Fraxtal DEX WFRAX_fraxtal <-> frxUSD_fraxtal

    We use:
      - qty_fxs for Binance and ETH DEX legs
      - qty_wfrax for Fraxtal legs

    Profits are in stable units, treated as USDT-equivalent.
    """
    client = make_binance_client(use_testnet=use_testnet)

    scenarios: List[ArbScenario] = []

    # ===== Binance & ETH DEX on WFRAX =====
    b_buy_cost = binance_buy_cost_usdt(client, binance_symbol, qty_fxs)
    b_sell_proceeds = binance_sell_proceeds_usdt(client, binance_symbol, qty_fxs)

    e_buy_cost = dex_eth_buy_cost_stable_fx("WFRAX", qty_fxs)
    e_sell_proceeds = dex_eth_sell_proceeds_stable_fx("WFRAX", qty_fxs)

    # Scenario 1: Buy on Binance, sell on ETH DEX (FXS)
    profit = e_sell_proceeds - b_buy_cost
    scenarios.append(
        ArbScenario(
            description="Buy FXS on Binance, sell WFRAX on ETH DEX (frxUSD)",
            profit_usdt_equiv=profit,
            leg1=f"BUY {qty_fxs} FXS on Binance ({binance_symbol}) for ~{b_buy_cost:.4f} USDT",
            leg2=f"SELL {qty_fxs} WFRAX on ETH DEX for ~{e_sell_proceeds:.4f} frxUSD",
        )
    )

    # Scenario 2: Buy on ETH DEX, sell on Binance (FXS)
    profit = b_sell_proceeds - e_buy_cost
    scenarios.append(
        ArbScenario(
            description="Buy WFRAX on ETH DEX (frxUSD), sell FXS on Binance",
            profit_usdt_equiv=profit,
            leg1=f"BUY {qty_fxs} WFRAX on ETH DEX for ~{e_buy_cost:.4f} frxUSD",
            leg2=f"SELL {qty_fxs} FXS on Binance ({binance_symbol}) for ~{b_sell_proceeds:.4f} USDT",
        )
    )

    # ===== Fraxtal DEX on WFRAX =====
    f_buy_cost = dex_fraxtal_buy_cost_stable_wfrax(qty_wfrax)
    f_sell_proceeds = dex_fraxtal_sell_proceeds_stable_wfrax(qty_wfrax)

    # Scenario 3: Buy WFRAX on Fraxtal, sell FXS on Binance
    profit = b_sell_proceeds - f_buy_cost
    scenarios.append(
        ArbScenario(
            description="Buy WFRAX on Fraxtal (frxUSD_fraxtal), sell FXS on Binance",
            profit_usdt_equiv=profit,
            leg1=(
                f"BUY {qty_wfrax} WFRAX_fraxtal on Fraxtal DEX "
                f"for ~{f_buy_cost:.4f} frxUSD_fraxtal"
            ),
            leg2=f"SELL {qty_fxs} FXS on Binance ({binance_symbol}) for ~{b_sell_proceeds:.4f} USDT",
        )
    )

    # Scenario 4: Buy FXS on Binance, sell WFRAX on Fraxtal
    profit = f_sell_proceeds - b_buy_cost
    scenarios.append(
        ArbScenario(
            description="Buy FXS on Binance, sell WFRAX on Fraxtal (frxUSD_fraxtal)",
            profit_usdt_equiv=profit,
            leg1=f"BUY {qty_fxs} FXS on Binance ({binance_symbol}) for ~{b_buy_cost:.4f} USDT",
            leg2=(
                f"SELL {qty_wfrax} WFRAX_fraxtal on Fraxtal DEX "
                f"for ~{f_sell_proceeds:.4f} frxUSD_fraxtal"
            ),
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
    qty_wfrax: float,
):
    for s in scenarios:
        if s.profit_usdt_equiv <= min_profit:
            continue

        msg = (
            f"*Arb Opportunity Detected*\n\n"
            f"*Binance Market:* `{binance_symbol}`\n"
            f"*Size FXS:* `{qty_fxs}` tokens\n"
            f"*Size WFRAX_fraxtal:* `{qty_wfrax}` tokens\n"
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
    QTY_FXS = 1000.0      # FXS on Binance / ETH
    QTY_WFRAX = 1000.0    # WFRAX on Fraxtal

    # MIN_PROFIT_ALERT = 10.0  # USDT-equivalent
    MIN_PROFIT_ALERT = -10.0  # USDT-equivalent

    scenarios = find_arb_for_qty(
        qty_fxs=QTY_FXS,
        qty_wfrax=QTY_WFRAX,
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
            qty_wfrax=QTY_WFRAX,
        )
    else:
        print("Telegram notifier not configured; skipping alerts.")

