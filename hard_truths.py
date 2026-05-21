"""
hard_truths.py — 建構 hard_truths + regime 分類 + 分級呈現
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _number_or_default(value, default: float = 0.0) -> float:
    """Return a numeric value, falling back when upstream data is missing."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────
# Regime 分類
# ─────────────────────────────────────────────────────────────────────

def classify_regime(h: dict) -> str:
    """
    枚舉值：RISK_ON_GROWTH / RISK_OFF_RECESSION /
            INFLATIONARY_GROWTH / STAGFLATION /
            GOLDILOCKS / POLICY_TRANSITION
    """
    real_yield_up  = h.get("real_yield_direction") == "up"
    curve_inverted = h.get("yield_curve_inverted", False)
    credit_stress  = h.get("credit_stress", False)
    spx_up         = h.get("SPX_direction") == "up"
    inflation_high = _number_or_default(h.get("forward_5y5y"), 2.0) > 2.5
    fed_cutting    = _number_or_default(h.get("fed_cuts_priced_in"), 0) > 1
    cli_slowing    = h.get("oecd_cli_direction") in ("slowing", "contracting")

    if credit_stress and not spx_up:
        return "RISK_OFF_RECESSION"
    if curve_inverted and credit_stress:
        return "RISK_OFF_RECESSION"
    if inflation_high and (not spx_up or cli_slowing):
        return "STAGFLATION"
    if inflation_high and real_yield_up:
        return "INFLATIONARY_GROWTH"
    if fed_cutting and not inflation_high and spx_up:
        return "GOLDILOCKS"
    if not inflation_high and not credit_stress and spx_up:
        return "RISK_ON_GROWTH"
    return "POLICY_TRANSITION"


# ─────────────────────────────────────────────────────────────────────
# Real Yield Direction (需要昨天的資料比較)
# ─────────────────────────────────────────────────────────────────────

def compute_real_yield_direction(current: Optional[float],
                                  previous: Optional[float] = None) -> str:
    """計算實質利率方向。"""
    if current is None or previous is None:
        return "flat"
    current_value = _number_or_default(current, None)
    previous_value = _number_or_default(previous, None)
    if current_value is None or previous_value is None:
        return "flat"
    diff = current_value - previous_value
    if diff > 0.03:
        return "up"
    elif diff < -0.03:
        return "down"
    return "flat"


# ─────────────────────────────────────────────────────────────────────
# Fiscal Dominance Risk
# ─────────────────────────────────────────────────────────────────────

def compute_fiscal_dominance(h: dict) -> bool:
    """debt/GDP > 100% 且赤字擴張 → fiscal dominance risk。"""
    debt_gdp = _number_or_default(h.get("imf_us_debt_gdp"), None)
    fiscal_bal = _number_or_default(h.get("imf_us_fiscal_balance"), None)

    if debt_gdp is None or fiscal_bal is None:
        return False
    return debt_gdp > 100 and fiscal_bal < -3.0


# ─────────────────────────────────────────────────────────────────────
# 建構完整 hard_truths
# ─────────────────────────────────────────────────────────────────────

def build_hard_truths(raw_data: dict,
                      prev_real_yield: Optional[float] = None) -> dict:
    """從 raw_data 建構完整的 hard_truths dict。"""
    h = dict(raw_data)  # 複製

    # Real yield direction
    h["real_yield_direction"] = compute_real_yield_direction(
        h.get("real_yield_value"), prev_real_yield
    )

    # Fiscal dominance
    h["fiscal_dominance_risk"] = compute_fiscal_dominance(h)

    # Liquidity direction (需要歷史比較，暫時用 net_liquidity_change)
    net_liq_change = _number_or_default(h.get("net_liquidity_change"), 0)
    if net_liq_change > 10:
        h["liquidity_direction"] = "injecting"
    elif net_liq_change < -10:
        h["liquidity_direction"] = "draining"
    else:
        h["liquidity_direction"] = "neutral"

    # Regime
    h["current_regime"] = classify_regime(h)

    return h


# ─────────────────────────────────────────────────────────────────────
# 分級呈現
# ─────────────────────────────────────────────────────────────────────

REGIME_FRAMEWORKS = {
    "RISK_OFF_RECESSION":   "Fisher Equation + Liquidity Cycle + Duration Risk",
    "INFLATIONARY_GROWTH":  "Taylor Rule + Supply Shock + DCF壓縮",
    "STAGFLATION":          "Mundell-Fleming + Power Transition",
    "GOLDILOCKS":           "DCF支撐 + Reflexivity",
    "POLICY_TRANSITION":    "Fed Reaction Function + Market Pricing Gap",
    "RISK_ON_GROWTH":       "Liquidity Cycle + Reflexivity + Momentum",
}


def format_level_a(h: dict) -> str:
    """Level A：永遠顯示的核心指標。"""
    lines = []

    regime = h.get("current_regime", "UNKNOWN")
    cli_dir = h.get("oecd_cli_direction", "N/A")
    fiscal_dom = "⚠️ YES" if h.get("fiscal_dominance_risk") else "No"

    lines.append(f"═══ LEVEL A (核心) ═══")
    lines.append(f"Regime: {regime}")
    lines.append(f"推薦框架: {REGIME_FRAMEWORKS.get(regime, 'N/A')}")
    lines.append(f"OECD CLI 方向: {cli_dir}")
    lines.append(f"Fiscal Dominance Risk: {fiscal_dom}")
    lines.append("")

    # 政策
    rff = h.get("real_fed_funds")
    taylor = h.get("taylor_rule_deviation")
    lines.append(f"Real Fed Funds: {rff}")
    lines.append(f"Taylor Rule Deviation: {taylor}")
    lines.append("")

    # 流動性
    liq_dir = h.get("liquidity_direction", "N/A")
    lines.append(f"Liquidity Direction: {liq_dir}")
    lines.append("")

    # 風險定價
    ry = h.get("real_yield_value")
    ry_dir = h.get("real_yield_direction")
    yc = h.get("yield_curve_value")
    yc_inv = h.get("yield_curve_inverted")
    cs = h.get("credit_stress")
    cuts = h.get("fed_cuts_priced_in")

    lines.append(f"Real Yield: {ry} ({ry_dir})")
    lines.append(f"Yield Curve (10Y-2Y): {yc} ({'INVERTED' if yc_inv else 'normal'})")
    lines.append(f"Credit Stress: {'YES' if cs else 'No'}")
    lines.append(f"Fed Cuts Priced In: {cuts}")
    lines.append("")

    # 資產方向
    for asset in ["SPX", "Brent", "Gold", "DXY", "UST10Y"]:
        price = h.get(f"{asset}_price")
        pct = h.get(f"{asset}_pct")
        direction = h.get(f"{asset}_direction")
        if price is not None:
            lines.append(f"{asset}: {price} ({pct:+.2f}%, {direction})")

    # GDPNow
    gdp = h.get("gdpnow_estimate")
    if gdp is not None:
        lines.append(f"\nGDPNow Estimate: {gdp}%")

    return "\n".join(lines)


def format_level_b(h: dict) -> str:
    """Level B：異常才顯示。"""
    lines = []

    # COT 擁擠
    cot = h.get("cot_crowding_flags", [])
    if cot:
        lines.append(f"⚠️ COT 極端倉位: {', '.join(cot)}")

    # 流動性大幅變化
    net_liq_change = _number_or_default(h.get("net_liquidity_change"), 0)
    if abs(net_liq_change) > 30:
        lines.append(f"⚠️ 淨流動性週變化: ${net_liq_change:.0f}B")

    # VIX term ratio 異常
    vtr = h.get("vix_term_ratio")
    if vtr is not None and (vtr < 0.8 or vtr > 1.3):
        lines.append(f"⚠️ VIX Term Ratio: {vtr} ({'短期恐慌' if vtr > 1.3 else '期限結構倒掛'})")

    # Fiscal dominance
    if h.get("fiscal_dominance_risk"):
        lines.append(f"⚠️ Fiscal Dominance Risk: debt/GDP={h.get('imf_us_debt_gdp')}%, "
                     f"fiscal balance={h.get('imf_us_fiscal_balance')}%")

    if lines:
        return "═══ LEVEL B (異常觸發) ═══\n" + "\n".join(lines)
    return ""
