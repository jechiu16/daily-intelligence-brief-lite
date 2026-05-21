"""
logic_guardrail.py — Logic Guardrail (Gemini 2.5 Flash)
"""

import logging

from config import GOOGLE_API_KEY, MODEL_FLASH

logger = logging.getLogger(__name__)

client = None


def _get_client():
    global client
    if client is None:
        from google import genai
        client = genai.Client(api_key=GOOGLE_API_KEY)
    return client


def _build_generate_config():
    from google.genai import types

    return types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=1000,
        thinking_config=types.ThinkingConfig(
            thinking_budget=1000
        ),
    )


def build_guardrail_prompt(draft, hard_truths):
    check_fields = {
        "real_yield_direction": hard_truths.get("real_yield_direction"),
        "real_yield_value": hard_truths.get("real_yield_value"),
        "yield_curve_inverted": hard_truths.get("yield_curve_inverted"),
        "yield_curve_value": hard_truths.get("yield_curve_value"),
        "credit_stress": hard_truths.get("credit_stress"),
        "current_regime": hard_truths.get("current_regime"),
        "SPX_direction": hard_truths.get("SPX_direction"),
        "SPX_pct": hard_truths.get("SPX_pct"),
        "Gold_direction": hard_truths.get("Gold_direction"),
        "DXY_direction": hard_truths.get("DXY_direction"),
        "Brent_direction": hard_truths.get("Brent_direction"),
        "UST10Y_direction": hard_truths.get("UST10Y_direction"),
        "liquidity_direction": hard_truths.get("liquidity_direction"),
    }

    return f"""你是事實校驗員。比對草稿中的方向描述是否與 hard_truths 一致。

═══ hard_truths ═══
{check_fields}

═══ 草稿 ═══
{draft[:3000]}

═══ 任務 ═══
逐一檢查：實質利率方向、殖利率曲線、信用壓力、各資產方向、Regime。
全部一致輸出 PASS。不一致每個問題輸出一行：[指標] 草稿說[X]，hard_truths是[Y]
"""


def run_logic_guardrail(draft, hard_truths):
    logger.info("Running Logic Guardrail (Gemini Flash)...")
    prompt = build_guardrail_prompt(draft, hard_truths)

    try:
        response = _get_client().models.generate_content(
            model=MODEL_FLASH,
            contents=prompt,
            config=_build_generate_config(),
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
        return False, f"Guardrail degraded error: {e}"
