"""
relational_guardrail.py — 純 Python，零 LLM
偵測跨資產邏輯矛盾，注入 Analyst context。
"""

import logging
from typing import Callable, Union

logger = logging.getLogger(__name__)


def _compute_regime_signal(h: dict) -> str:
    """Regime 一致性檢查。"""
    regime = h.get("current_regime", "")
    messages = []

    if regime == "RISK_ON_GROWTH":
        if h.get("yield_curve_inverted"):
            messages.append("Regime=RISK_ON_GROWTH 但殖利率曲線倒掛，注意衰退訊號")
        if h.get("credit_stress"):
            messages.append("Regime=RISK_ON_GROWTH 但信用壓力存在，regime 可能誤判")

    if regime == "RISK_OFF_RECESSION":
        if h.get("SPX_direction") == "up" and (h.get("SPX_pct", 0) > 1):
            messages.append("Regime=RISK_OFF_RECESSION 但 SPX 大漲，可能是 bear market rally")

    if regime == "GOLDILOCKS":
        if h.get("forward_5y5y", 2.0) > 2.5:
            messages.append("Regime=GOLDILOCKS 但遠期通膨預期偏高，Goldilocks 可能不持久")

    if messages:
        return "⚡ " + " | ".join(messages)
    return ""


# ── 規則定義 ─────────────────────────────────────────────────────────

RuleType = tuple[str, Callable, Union[str, Callable]]

RULES: list[RuleType] = [
    (
        "SPX↑ + 實質利率↑",
        lambda h: h.get("SPX_pct", 0) > 0.5 and h.get("real_yield_direction") == "up",
        "⚡ SPX↑+實質利率↑違反DCF邏輯，必須定調為倉位回補或流動性驅動",
    ),
    (
        "Gold↑ + 實質利率↑",
        lambda h: h.get("Gold_direction") == "up" and h.get("real_yield_direction") == "up",
        "⚡ Gold↑+實質利率↑歷史負相關。央行購金？地緣溢價？",
    ),
    (
        "SPX↑ + VIX↑>3%",
        lambda h: h.get("SPX_pct", 0) > 0.5 and h.get("VIX_pct", 0) > 3.0,
        "⚡ 股指與恐慌指數同漲。Short squeeze？",
    ),
    (
        "油崩 + 通膨預期未等比下修",
        lambda h: (h.get("Brent_pct", 0) < -5
                   and abs(h.get("forward_5y5y", 2.0) - 2.0) > 0.15),
        "⚡ 油崩但通膨預期頑強。服務通膨黏性？",
    ),
    (
        "COT極端擁擠",
        lambda h: len(h.get("cot_crowding_flags", [])) > 0,
        lambda h: f"⚡ {h['cot_crowding_flags']} 倉位極端擁擠，反轉風險高",
    ),
    (
        "流動性收縮 + SPX↑",
        lambda h: (h.get("liquidity_direction") == "draining"
                   and h.get("SPX_direction") == "up"),
        "⚡ 淨流動性收縮但美股上漲，注意持續性",
    ),
    (
        "DXY↓ + 實質利率↑",
        lambda h: (h.get("DXY_direction") == "down"
                   and h.get("real_yield_direction") == "up"),
        "⚡ 美元↓+實質利率↑背離正常，資本外流？美元信用問題？",
    ),
    (
        "HY spread擴張 + SPX↑",
        lambda h: (h.get("credit_stress", False)
                   and h.get("SPX_direction") == "up"),
        "⚡ 信用市場壓力與股市樂觀並存，regime mismatch",
    ),
    (
        "Regime計數",
        lambda h: True,
        _compute_regime_signal,
    ),
]


def run_relational_guardrail(hard_truths: dict) -> list[str]:
    """
    執行所有規則，返回觸發的 flag 列表。
    這些 flag 會注入 Analyst 的 context。
    """
    flags = []

    for name, condition, message in RULES:
        try:
            if condition(hard_truths):
                if callable(message):
                    msg = message(hard_truths)
                else:
                    msg = message

                if msg:  # 有些動態 message 可能返回空字串
                    flags.append(msg)
                    logger.info(f"Relational flag triggered: {name}")
        except Exception as e:
            logger.warning(f"Relational rule '{name}' error: {e}")

    return flags
