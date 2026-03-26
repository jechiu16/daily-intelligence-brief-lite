"""
analyst.py — Analyst 模組 (Gemini 2.5 Pro)
"""

import logging

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL_ANALYST

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GOOGLE_API_KEY)

FRAMEWORK_LIBRARY = """
【貨幣政策】
Fisher Equation: 名目利率 = 實質利率 + 通膨預期
Taylor Rule: 政策利率 = 中性利率 + 1.5×(通膨-目標) + 0.5×(產出缺口)

【資產定價】
DCF: 實質利率↑ → 折現率↑ → 高估值資產承壓
Duration Risk: 長端利率波動對長存續期資產的非線性衝擊

【流動性】
Liquidity Cycle: 淨流動性 → 資產價格
Reflexivity: 市場定價影響基本面，基本面再影響定價

【地緣政治 / 國際政治經濟】
Supply Shock vs Demand Shock: 供給衝擊→滯脹，需求衝擊→衰退
Power Transition Theory: 崛起大國 vs 既有大國的結構性衝突
Fiscal Dominance: 財政壓力如何侵蝕貨幣政策獨立性？
"""


def build_analyst_prompt(
    level_a, level_b, relational_flags, regime, framework,
    l1, l2, l3, kh, periphery_label, periphery_keywords,
):
    l1_block = ""
    if l1.get("yesterday_headline"):
        l1_block = f"\nL1（昨日摘要）：\n  昨日主題：{l1['yesterday_headline']}\n  昨日術語：{l1['yesterday_term']}\n  昨日行動建議：{l1['yesterday_action']}\n"

    l2_block = f"\nL2（本週市場結構）：\n{l2}\n" if l2 else ""

    l3_block = ""
    if l3:
        l3_block = "\nL3（現有 Active Thesis）：\n"
        for t in l3:
            l3_block += f"  - {t['name']}: {t['statement']} (confidence={t.get('confidence', '?')})\n"

    kh_block = ""
    if kh:
        used_terms = [item["term"] for item in kh]
        kh_block = f"\nKH（已用過的術語，避免重複）：{', '.join(used_terms)}\n"

    flags_block = ""
    if relational_flags:
        flags_block = "\n⚡ Relational Flags（必須在分析中處理）：\n"
        for f in relational_flags:
            flags_block += f"  {f}\n"

    return f"""你是 Daily Intelligence Brief 的首席分析師。
你的任務是對今天的宏觀環境做嚴謹分析，產出結構化草稿。
這個草稿是給 Narrator（白話翻譯者）用的，不是給讀者看的。你可以用術語。

{level_a}

{level_b}
{flags_block}

Regime: {regime}
推薦框架: {framework}
{FRAMEWORK_LIBRARY}
{l1_block}{l2_block}{l3_block}{kh_block}

今日邊陲地區：{periphery_label}
邊陲搜尋關鍵字：{periphery_keywords}
→ 請搜尋這個地區的最新動態，寫入邊陲段落。

══════════════════════════════════════════════════
請產出以下結構化草稿（繁體中文）：

## 1. 今天最重要的一件事
一句話概括。

## 2. 完整因果鏈
用「因為...所以...」邏輯串連。包含框架名稱。

## 3. 誰受影響
分三類：持有股票的人 / 持有債券或定存的人 / 持有外幣的人
每類標記：🔴需要關注 / 🟡保持觀察 / 🟢目前穩定

## 4. 結構化攻擊
選擇 regime_misclassification 或 second_order_inversion 執行。
格式：攻擊類型 / 攻擊內容 / 反面訊號

## 5. 今日術語建議
不在 KH 已用列表中、今天有用到、可以用日常比喻解釋。

## 6. 邊陲段落：{periphery_label}
在哪、多少人、正在發生什麼、跟市場有沒有關係。

## 7. Thesis 更新
現有 thesis 更新 + 新 thesis（JSON 格式）

## 8. L2 更新建議
regime / driver / policy / fragility
"""


def run_analyst(prompt):
    logger.info("Running Analyst (Gemini 2.5 Pro)...")
    try:
        response = client.models.generate_content(
            model=MODEL_ANALYST,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=8000,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=8000
                ),
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        text_parts = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                if not getattr(part, "thought", False):
                    text_parts.append(part.text)

        result = "\n".join(text_parts)
        logger.info(f"Analyst output: {len(result)} chars")
        return result

    except Exception as e:
        logger.error(f"Analyst error: {e}")
        raise
