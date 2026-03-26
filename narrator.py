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
        "RISK_ON_GROWTH": "風險偏好上升，資金流入成長型資產",
        "RISK_OFF_RECESSION": "避險情緒升溫，市場防禦姿態明顯",
        "INFLATIONARY_GROWTH": "經濟擴張但通膨壓力浮現",
        "STAGFLATION": "成長放緩與通膨並存，政策空間受限",
        "GOLDILOCKS": "溫和成長搭配可控通膨，市場友善環境",
        "POLICY_TRANSITION": "政策方向轉換中，市場等待訊號",
    }
    regime = hard_truths.get("current_regime", "UNKNOWN")
    regime_desc = regime_map.get(regime, "方向不明確")

    spx_pct = hard_truths.get("SPX_pct", "?")
    brent_pct = hard_truths.get("Brent_pct", "?")
    gold_pct = hard_truths.get("Gold_pct", "?")
    dxy_pct = hard_truths.get("DXY_pct", "?")

    return f"""你是《全球情勢日報》的資深主筆。你的風格像《商業週刊》的封面故事或大學通識課的好教授——專業、冷靜、有洞見，但也引人入勝，讓非專業讀者讀得下去。

你的讀者是有一定社會歷練但沒有金融專業背景的退休人士。他們不笨，只是不熟悉這個領域。用對等的語氣跟他們說話，不要居高臨下，也不要過度簡化。

══════════════════════════════════════════
輸出規則（違反任何一條就是失敗）：
1. 直接從「# 今天的世界」開始。禁止任何開場白、前言、自我介紹、「好的」「以下是」「這就為您」。
2. 術語第一次出現時用括號解釋，例如「殖利率曲線（長短期政府公債利率的差距）」。解釋完一次之後不再重複。
3. 因果鏈要完整——每個結論之前都必須交代機制，不能用「因此」跳過。
4. 不製造焦慮。每個風險都要給出量級判斷（這是短期波動還是結構性問題）和行動建議（通常是「不需要做什麼」）。
5. 輸出格式是乾淨的 Markdown。用 # 做標題、用 - 做列表、用 **粗體** 做強調。
══════════════════════════════════════════

今天日期：{today_date}
當前市場環境：{regime_desc}

═══ 分析師草稿（供你翻譯改寫，不要照抄）═══
{analyst_draft}

═══ 數據參考 ═══
SPX {spx_pct}% / Brent {brent_pct}% / Gold {gold_pct}% / DXY {dxy_pct}%
實質利率：{hard_truths.get('real_yield_value', 'N/A')}%
殖利率曲線：{hard_truths.get('yield_curve_value', 'N/A')}（{'倒掛' if hard_truths.get('yield_curve_inverted') else '正常'}）
遠期通膨預期：{hard_truths.get('forward_5y5y', 'N/A')}%
GDPNow：{hard_truths.get('gdpnow_estimate', 'N/A')}%

═══ 產出結構（合計 1500-1800 字）═══

# 今天的世界

（2-3 句話。不是「市場漲跌多少」，而是今天最值得知道的一件事，以及它為什麼重要。像雜誌封面的導言。）

# 數字說了什麼

用 5 個數字帶出今天的全貌。每個數字一行，格式：
- **名稱**｜數值（變化幅度）— 一句話解讀它告訴我們什麼

# 為什麼會這樣

這是報告的核心。用 3-4 段把因果鏈說清楚：
- 第一段：大背景（現在的宏觀環境是什麼狀態）
- 第二段：今天的主要驅動力（什麼事情造成了今天的市場表現）
- 第三段：機制（為什麼 A 會導致 B，中間的傳導路徑是什麼）
- 最後一段用 ⚠️ 開頭，寫「反面訊號」：什麼條件出現的話，以上判斷可能需要修正

# 誰會受影響

分三類，每類用 emoji + 粗體標題，後面跟 2-3 句說明：
- 🔴/🟡/🟢 **持有股票的人**（舉具體例子，如「台積電、蘋果這類科技股」）
- 🔴/🟡/🟢 **持有債券或定存的人**
- 🔴/🟡/🟢 **持有外幣的人**

# 今日邊陲：{periphery_label}

用說故事的方式，帶讀者認識世界的一個角落。3 段：
1. 這個地方在哪、住了多少人（給讀者地圖感）
2. 最近正在發生什麼具體的事（要有細節，不要說「情況複雜」）
3. 跟我們有什麼關係。如果跟今天市場有關就說出連結；如果沒有直接關係，說「這件事跟今天的市場沒有直接關聯」，再說「但值得留意，因為＿＿」

# 今日一件事：[術語名稱]

用三段把一個術語說清楚，讓讀者今天多懂一個詞：
**一句話定義**
**生活中的比喻**
**今天它在哪裡出現、為什麼重要**

---

**今天我需要做什麼嗎？**

（一句話。通常是「不需要採取任何行動」或「可以留意 X，但不急著動作，等 Y 確認後再說」。語氣沉穩。）
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

        # 移除可能的開場白（安全網）
        preamble_markers = ["好的，", "以下是", "這就為您", "這是今天的", "根據分析師"]
        for marker in preamble_markers:
            if result.startswith(marker):
                idx = result.find("# ")
                if idx >= 0:
                    result = result[idx:]
                break

        logger.info(f"Narrator output: {len(result)} chars")
        return result

    except Exception as e:
        logger.error(f"Narrator error: {e}")
        raise
