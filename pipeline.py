"""
pipeline.py — 主流程編排
每日執行一次，按順序：資料 → 分析 → 校驗 → 翻譯 → 更新記憶層
"""

import datetime
import logging

from data_layer import collect_all_data
from date_utils import taipei_today
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
from knowledge_terms import select_knowledge_candidates

logger = logging.getLogger(__name__)


def run_daily_pipeline(manual_date: str | None = None) -> str:
    """
    執行完整的每日 pipeline。
    返回最終報告文字。
    """
    today = manual_date or taipei_today().isoformat()
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

    knowledge_context = "\n".join([
        level_a,
        level_b,
        regime,
        framework,
        periphery_label,
        periphery_keywords,
        " ".join(relational_flags),
    ])
    knowledge_candidates = select_knowledge_candidates(
        knowledge_context,
        used_terms=kh,
        limit=8,
    )

    # ── Step 5 & 6: Analyst & Logic Guardrail (具備重試與阻斷機制) ─
    base_analyst_prompt = build_analyst_prompt(
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
        knowledge_candidates=knowledge_candidates,
    )
    
    current_prompt = base_analyst_prompt
    max_retries = 2
    attempt = 0
    passed = False
    analyst_draft = ""

    while attempt <= max_retries:
        logger.info(f"Step 5: Analyst (嘗試次數 {attempt + 1}/{max_retries + 1})")
        analyst_draft = run_analyst(current_prompt)

        logger.info(f"Step 6: Logic Guardrail (嘗試次數 {attempt + 1}/{max_retries + 1})")
        passed, guardrail_message = run_logic_guardrail(analyst_draft, hard_truths)

        if passed:
            logger.info("Logic Guardrail 驗證通過！")
            break
        else:
            logger.warning(f"Logic Guardrail 發現問題 (嘗試 {attempt + 1}):\n{guardrail_message}")
            attempt += 1
            if attempt <= max_retries:
                logger.info("將錯誤反饋給 Analyst，準備重新生成草稿...")
                # 將護欄的警告加到 Prompt 的最後，要求 AI 修正
                current_prompt = base_analyst_prompt + (
                    f"\n\n⚠️ 【重要修正要求】\n"
                    f"你前一次生成的草稿未能通過邏輯校驗，因為與原始數據(hard_truths)產生矛盾。\n"
                    f"請仔細閱讀以下錯誤報告，並重新生成一份**完全符合數據事實**的草稿：\n"
                    f"{guardrail_message}"
                )
            else:
                logger.error("已達最大重試次數，Logic Guardrail 依然不通過，強制終止 Pipeline。")
                # 強制拋出錯誤，觸發 main.py 的 sys.exit(1)，阻斷發布
                raise ValueError(f"Pipeline 強制終止：Analyst 連續 {max_retries + 1} 次未能通過邏輯校驗。\n最後一次錯誤原因：\n{guardrail_message}")

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
    save_daily_report(today, final_report,
                      regime=regime, periphery=periphery_label)

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

    prompt = f"""你是 Daily Intelligence Brief 的週報主筆。
讀者是受過良好教育、關心世界局勢，但不一定有金融或總經背景的一般讀者。語言要成熟、清楚、有知識感，不要投資喊單。

═══ 本週市場結構 (L2) ═══
{l2}

═══ 現有追蹤線索 (L3) ═══
{[t for t in l3 if t.get('status') == 'active']}

═══ 本週學到的詞 (KH) ═══
{terms_this_week}

請產出週報，結構：

## 這週最重要的一件事
（從 L2 中歸納本週最顯著的趨勢或事件，一段話）

## 這週我學到的新詞
（回顧本週「今日一件事」的術語，每個用一句話複習）

## 下週可以留意什麼
（1-2 個，不超過。從 L3 active thesis 中挑選最值得關注的世界線索）

📋 這週可以怎麼理解？
（一句話收束，不給投資指令）

語言：繁體中文，成熟清楚。
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
