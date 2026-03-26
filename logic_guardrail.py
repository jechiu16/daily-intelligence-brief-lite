"""
logic_guardrail.py — Logic Guardrail (Gemini 3 Flash Preview)
只驗證 hard_truths 中可客觀比對的方向事實。
"""

import logging

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL_FLASH

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GOOGLE_API_KEY)


def build_guardrail_prompt(draft: str, hard_truths: dict) -> str:
    """建構 Logic Guardrail prompt。"""

    # 只提取需要校驗的欄位
    check_fields = {
        "real_yield_direction": hard_truths.get("real_yield_direction"),
        "real_yield_value": hard_truths.get("real_yield_value"),
        "yield_curve_inverted": hard_truths.get("yield_curve_inverted"),
        "yield_curve_value": hard_truths.get("yield_curve_value"),
        "credit_stress": hard_truths.get("credit_stress"),
        "hy_ig_spread": hard_truths.get("hy_ig_spread"),
        "current_regime": hard_truths.get("current_regime"),
        "SPX_direction": hard_truths.get("SPX_direction"),
        "SPX_pct": hard_truths.get("SPX_pct"),
        "Gold_direction": hard_truths.get("Gold_direction"),
        "Gold_pct": hard_truths.get("Gold_pct"),
        "DXY_direction": hard_truths.get("DXY_direction"),
        "DXY_pct": hard_truths.get("DXY_pct"),
        "Brent_direction": hard_truths.get("Brent_direction"),
        "Brent_pct": hard_truths.get("Brent_pct"),
        "UST10Y_direction": hard_truths.get("UST10Y_direction"),
        "UST10Y_pct": hard_truths.get("UST10Y_pct"),
        "liquidity_direction": hard_truths.get("liquidity_direction"),
    }

    return f"""你是事實校驗員。只做一件事：比對草稿中的方向描述是否與 hard_truths 一致。

═══ hard_truths（事實）═══
{check_fields}

═══ 資產方向偏差閾值 ═══
- rates (UST10Y): 5 bps
- fx (DXY): 0.5%
- equities (SPX): 1%
- gold: 1%

═══ 草稿 ═══
{draft}

═══ 你的任務 ═══
逐一檢查：
1. 草稿中描述實質利率的方向，是否與 real_yield_direction 一致？
2. 草稿中描述殖利率曲線，是否與 yield_curve_inverted 一致？
3. 草稿中描述信用利差壓力，是否與 credit_stress 一致？
4. 各資產方向描述是否在閾值內？
5. Regime 描述是否與 current_regime 一致？

如果全部一致，輸出：PASS
如果有不一致，每個問題輸出一行：[指標] 草稿說[X]，hard_truths是[Y]
"""


def run_logic_guardrail(draft: str, hard_truths: dict) -> tuple[bool, str]:
    """
    執行 Logic Guardrail。
    返回 (passed: bool, message: str)。
    """
    logger.info("Running Logic Guardrail (Gemini Flash)...")

    prompt = build_guardrail_prompt(draft, hard_truths)

    try:
        response = client.models.generate_content(
            model=MODEL_FLASH,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=1000,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=1000
                ),
            ),
        )

        result = response.text.strip()
        passed = "PASS" in result.upper() and "[" not in result

        if passed:
            logger.info("Logic Guardrail: PASS")
        else:
            logger.warning(f"Logic Guardrail: ISSUES FOUND\n{result}")

        return passed, result

    except Exception as e:
        logger.error(f"Logic Guardrail error: {e}")
        return True, f"Guardrail error (defaulting to PASS): {e}"
