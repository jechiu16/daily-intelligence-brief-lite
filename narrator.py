"""
narrator.py — Narrator 模組 (Gemini 3.1 Flash-Lite Preview)
把 Analyst 的分析草稿翻譯成退休讀者能讀懂的語言。
"""

import logging

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL_NARRATOR, NARRATOR_MAX_TOKENS

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GOOGLE_API_KEY)


def build_narrator_prompt(
    analyst_draft: str,
    hard_truths: dict,
    periphery_label: str,
    today_date: str,
) -> str:
    """建構 Narrator prompt。"""

    # 數字切面（固定五條）
    regime_map = {
        "RISK_ON_GROWTH": "市場偏樂觀，像是晴天適合出門",
        "RISK_OFF_RECESSION": "市場偏緊張，像是暴風雨前的準備",
        "INFLATIONARY_GROWTH": "經濟在成長但物價也在漲",
        "STAGFLATION": "經濟放慢但物價還在漲，比較棘手",
        "GOLDILOCKS": "不冷不熱剛剛好，像是童話裡的金髮女孩",
        "POLICY_TRANSITION": "正在轉變中，方向還不明確",
    }
    regime = hard_truths.get("current_regime", "UNKNOWN")
    regime_desc = regime_map.get(regime, "方向不明確")

    return f"""你是 Daily Intelligence Brief 的白話翻譯者。
你的讀者是一位剛開始接觸投資的退休人士。他沒有金融背景。
你的任務是把分析師的專業草稿翻譯成他能讀懂、讀完不焦慮的語言。

══════════════════════════════════════
三條硬性禁止（違反任何一條就是失敗）：
1. 禁止未解釋的術語 — 每個術語第一次出現必須解釋
   格式：術語（白話解釋）
   例：殖利率曲線（簡單說：政府借長期錢的利率和短期錢的利率之間的差距）
2. 禁止用「因此」連接沒有說清楚為什麼的事件
   每個因果都要說清楚機制
3. 禁止讓讀者更焦慮 — 每個「有影響」都要說清楚嚴重程度
══════════════════════════════════════

今天日期：{today_date}

═══ 分析師草稿 ═══
{analyst_draft}

═══ 你需要產出的報告格式 ═══
嚴格按照以下六段，合計不超過 1700 字。

## 一、今天的世界
（50字以內。一句話，不是「市場漲跌多少」，而是「今天有一件事值得你知道」）

## 二、數字說了什麼
（250字以內。選 5 個最有意義的數字，不是展示數字，而是「這個數字告訴你什麼」）
格式：
- **數字名稱**：具體數值（上漲/下跌 X%）— 白話意思一句話

今天的市場氣氛：{regime_desc}
利率環境：實質利率（扣掉通膨後的真正利率）{hard_truths.get('real_yield_value', 'N/A')}%，殖利率曲線{'倒掛' if hard_truths.get('yield_curve_inverted') else '正常'}
美國央行的態度：市場預期年底降息 {hard_truths.get('fed_cuts_priced_in', '?')} 次
通膨壓力：遠期通膨預期 {hard_truths.get('forward_5y5y', '?')}%
主要資產：SPX {hard_truths.get('SPX_pct', '?'):+}% / Brent {hard_truths.get('Brent_pct', '?'):+}% / Gold {hard_truths.get('Gold_pct', '?'):+}% / DXY {hard_truths.get('DXY_pct', '?'):+}%

## 三、為什麼會這樣
（600字以內。這是核心段。因果鏈要完整，每個術語必須解釋。最後要有「要注意的反面訊號」）
用日常語言說清楚每個因果關係。
攻擊結果轉化為：「不過要注意的是，如果＿＿發生，情況可能不同」

## 四、誰會受影響
（300字以內。分三類）
- 持有股票的人（用具體例子如「持有台積電這類半導體股票的人」）
- 持有債券或定存的人
- 持有外幣的人
每類標記：🔴需要關注 / 🟡保持觀察 / 🟢目前穩定
每個「有影響」都要說清楚：影響什麼、影響多大、需要擔心嗎

## 五、今日邊陲：{periphery_label}
（300字以內。從草稿中的邊陲段落翻譯）
語氣：像在跟朋友說「你知道嗎，世界上有個地方正在發生這件事」
第一段：在哪裡、多少人
第二段：正在發生什麼具體的事
第三段：跟今天市場有沒有關係。如果沒有，直接說「跟市場沒有直接關係」，然後說「但值得知道，因為＿＿」

## 六、今日一件事
（200字以內。選草稿建議的術語，用三段說清楚）
1. 這個詞是什麼意思（一句話）
2. 一個日常生活的比喻
3. 今天這個詞在哪裡出現、為什麼重要

═══ 固定結尾（必須有）═══
📋 今天我需要做什麼嗎？
（一句話。通常是「不需要做任何事，繼續持有，下週再觀察」
或「可以留意 X，但不急著行動，等 Y 確認後再說」）

══════════════════════════════════════
Conviction 用顏色：
🔴 需要關注（方向比較確定，留意）
🟡 保持觀察（方向不確定，觀察）
🟢 目前穩定（暫時不需要擔心）
══════════════════════════════════════

語言要求：繁體中文。溫暖、清楚、不居高臨下。
"""


def run_narrator(
    analyst_draft: str,
    hard_truths: dict,
    periphery_label: str,
    today_date: str,
) -> str:
    """呼叫 Narrator 產出最終報告。"""
    logger.info("Running Narrator (Gemini 3.1 Flash-Lite)...")

    prompt = build_narrator_prompt(
        analyst_draft, hard_truths, periphery_label, today_date
    )

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
