"""
pipeline.py — 主流程編排
每日執行一次，按順序：資料 → 分析 → 校驗 → 翻譯 → 更新記憶層
"""

import datetime
import logging

from data_layer import collect_all_data
from hard_truths import build_hard_truths, format_level_a, format_level_b, REGIME_FRAMEWORKS
from relational_guardrail import run_relational_guardrail
from periphery import select_periphery
from memory_layer import (
    fetch_layer1, fetch_layer2, fetch_layer3,
    fetch_knowledge_history, save_daily_report,
)
from analyst import build_analyst_prompt, run_analyst
from logic_guardrail import run_logic_guardrail
from narrator import run_narrator
from layer_update import run_layer_update

logger = logging.getLogger(__name__)


def run_daily_pipeline(manual_date: str | None = None) -> str:
    """
    執行完整的每日 pipeline。
    返回最終報告文字。
    """
    today = manual_date or datetime.date.today().isoformat()
    logger.info(f"═══ Daily Intelligence Brief — {today} ═══")

    # ── Step 1: 資料收集 ──────────────────────────────────────────
    logger.info("Step 1: 資料收集")
    raw_data = collect_all_data()

    # ── Step 2: 建構 hard_truths ──────────────────────────────────
    logger.info("Step 2: 建構 hard_truths")
    hard_truths = build_hard_truths(raw_data)

    # ── Step 3: Relational Guardrail ──────────────────────────────
    logger.info("Step 3: Relational Guardrail")
    relational_flags = run_relational_guardrail(hard_truths)
    if relational_flags:
        logger.info(f"  觸發 {len(relational_flags)} 個 relational flags")

    # ── Step 4: 準備 context ──────────────────────────────────────
    logger.info("Step 4: 準備 context")

    level_a = format_level_a(hard_truths)
    level_b = format_level_b(hard_truths)

    periphery_label, periphery_keywords = select_periphery(
        datetime.date.fromisoformat(today)
    )
    logger.info(f"  今日邊陲: {periphery_label}")

    regime = hard_truths.get("current_regime", "POLICY_TRANSITION")
    framework = REGIME_FRAMEWORKS.get(regime, "N/A")

    l1 = fetch_layer1()
    l2 = fetch_layer2()
    l3 = fetch_layer3()
    kh = fetch_knowledge_history()

    # ── Step 5: Analyst ───────────────────────────────────────────
    logger.info("Step 5: Analyst")
    analyst_prompt = build_analyst_prompt(
        level_a=level_a,
        level_b=level_b,
        relational_flags=relational_flags,
        regime=regime,
        framework=framework,
        l1=l1,
        l2=l2,
        l3=l3,
        kh=kh,
        periphery_label=periphery_label,
        periphery_keywords=periphery_keywords,
    )
    analyst_draft = run_analyst(analyst_prompt)

    # ── Step 6: Logic Guardrail ───────────────────────────────────
    logger.info("Step 6: Logic Guardrail")
    passed, guardrail_message = run_logic_guardrail(analyst_draft, hard_truths)

    if not passed:
        logger.warning(f"Logic Guardrail failed:\n{guardrail_message}")
        # 將校驗結果追加到草稿，讓 Analyst 注意
        analyst_draft += f"\n\n⚠️ LOGIC GUARDRAIL CORRECTIONS:\n{guardrail_message}"
        # 在 v9-lite 中，我們不重跑 Analyst，但在草稿中標記問題
        # 未來可以加入重跑邏輯

    # ── Step 7: Narrator ──────────────────────────────────────────
    logger.info("Step 7: Narrator")
    final_report = run_narrator(
        analyst_draft=analyst_draft,
        hard_truths=hard_truths,
        periphery_label=periphery_label,
        today_date=today,
    )

    # ── Step 8: 儲存報告 ──────────────────────────────────────────
    logger.info("Step 8: 儲存報告")
    save_daily_report(today, final_report)

    # ── Step 9: 更新記憶層 ────────────────────────────────────────
    logger.info("Step 9: 更新記憶層")
    run_layer_update(
        analyst_draft=analyst_draft,
        final_report=final_report,
        hard_truths=hard_truths,
        today_date=today,
    )

    logger.info(f"═══ Pipeline 完成 — {today} ═══")
    return final_report


def run_weekly_report() -> str:
    """
    週報：比日報更簡單，讓讀者感覺「這週我有在關注世界」。
    """
    logger.info("═══ 週報生成 ═══")

    l2 = fetch_layer2()
    l3 = fetch_layer3()
    kh = fetch_knowledge_history()

    from google import genai
    from google.genai import types
    from config import GOOGLE_API_KEY, MODEL_NARRATOR

    client = genai.Client(api_key=GOOGLE_API_KEY)

    # 本週學到的詞
    terms_this_week = [item["term"] for item in kh[-7:]] if kh else []

    prompt = f"""你是 Daily Intelligence Brief 的週報翻譯者。
讀者是退休人士，語言要溫暖清楚。

═══ 本週市場結構 (L2) ═══
{l2}

═══ 現有 Thesis (L3) ═══
{[t for t in l3 if t.get('status') == 'active']}

═══ 本週學到的詞 (KH) ═══
{terms_this_week}

請產出週報，結構：

## 這週最重要的一件事
（從 L2 中歸納本週最顯著的趨勢或事件，一段話）

## 這週我學到的新詞
（回顧本週「今日一件事」的術語，每個用一句話複習）

## 下週要留意什麼
（1-2 個，不超過。從 L3 active thesis 中挑選最值得關注的）

📋 這週我需要做什麼嗎？
（通常是「不需要」或「可以留意 X」）

語言：繁體中文，溫暖清楚。
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NARRATOR,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,
                max_output_tokens=2000,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Weekly report error: {e}")
        raise
