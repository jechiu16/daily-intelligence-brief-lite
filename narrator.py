"""
narrator.py — Narrator 模組 (Gemini 2.5 Flash-Lite)
"""

import logging

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL_NARRATOR, NARRATOR_MAX_TOKENS

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GOOGLE_API_KEY)


def build_narrator_prompt(analyst_draft, hard_truths, periphery_label, today_date):
    regime_map = {
        "RISK_ON_GROWTH": "市場偏樂觀，像是晴天適合出門",
        "RISK_OFF_RECESSION": "市場偏緊張，像是暴風雨前的準備",
        "INFLATIONARY_GROWTH": "經濟在成長但物價也在漲",
        "STAGFLATION": "經濟放慢但物價還在漲，比較棘手",
        "GOLDILOCKS": "不冷不熱剛剛好",
        "POLICY_TRANSITION": "正在轉變中，方向還不明確",
    }
    regime = hard_truths.get("current_regime", "UNKNOWN")
    regime_desc = regime_map.get(regime, "方向不明確")

    spx_pct = hard_truths.get("SPX_pct", "?")
    brent_pct = hard_truths.get("Brent_pct", "?")
    gold_pct = hard_truths.get("Gold_pct", "?")
    dxy_pct = hard_truths.get("DXY_pct", "?")

    return f"""你是 Daily Intelligence Brief 的白話翻譯者。
讀者是退休人士，沒有金融背景。把分析師草稿翻譯成他能讀懂的語言。

三條硬性禁止：
1. 禁止未解釋的術語（第一次出現必須用白話解釋）
2. 禁止用「因此」跳過機制（每個因果都要說清楚為什麼）
3. 禁止讓讀者更焦慮（每個「有影響」都要說清楚嚴重程度）

今天日期：{today_date}

═══ 分析師草稿 ═══
{analyst_draft}

═══ 產出格式（六段，合計不超過 1700 字）═══

## 一、今天的世界
（50字內，一句話）

## 二、數字說了什麼
（250字內，5 個數字 + 白話）
市場氣氛：{regime_desc}
主要資產：SPX {spx_pct}% / Brent {brent_pct}% / Gold {gold_pct}% / DXY {dxy_pct}%

## 三、為什麼會這樣
（600字內，因果鏈 + 術語解釋 + 反面訊號）

## 四、誰會受影響
（300字內，持股/持債/持外幣，用🔴🟡🟢標記）

## 五、今日邊陲：{periphery_label}
（300字內，像跟朋友聊天）

## 六、今日一件事
（200字內，一個術語：意思 + 比喻 + 為什麼重要）

📋 今天我需要做什麼嗎？
（一句話，通常是「不需要做任何事」）

語言：繁體中文，溫暖清楚。
"""


def run_narrator(analyst_draft, hard_truths, periphery_label, today_date):
    logger.info("Running Narrator (Gemini Flash-Lite)...")
    prompt = build_narrator_prompt(analyst_draft, hard_truths, periphery_label, today_date)

    try:
        response = client.models.generate_content(
            model=MODEL_NARRATOR,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,
                max_output_tokens=NARRATOR_MAX_TOKENS,
            ),
        )

        result = response.text.strip()
        logger.info(f"Narrator output: {len(result)} chars")
        return result

    except Exception as e:
        logger.error(f"Narrator error: {e}")
        raise
