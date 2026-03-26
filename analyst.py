"""
analyst.py — Analyst 模組 (Gemini 3.1 Pro Preview)
在後台做嚴謹的宏觀分析，輸出草稿給 Narrator 翻譯。
"""

import json
import logging
from typing import Optional

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL_ANALYST

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GOOGLE_API_KEY)

# ── 分析框架庫 ───────────────────────────────────────────────────────

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
Credible Commitment Problem: 承諾為何不可信？約束機制是否存在？
Selectorate Theory: 領導人的政治存活邏輯如何扭曲政策？
Fiscal Dominance: 財政壓力如何侵蝕貨幣政策獨立性？
"""


def build_analyst_prompt(
    level_a: str,
    level_b: str,
    relational_flags: list[str],
    regime: str,
    framework: str,
    l1: dict,
    l2: str,
    l3: list[dict],
    kh: list[dict],
    periphery_label: str,
    periphery_keywords: str,
) -> str:
    """建構 Analyst 的完整 prompt。"""

    # 記憶層
    l1_block = ""
    if l1.get("yesterday_headline"):
        l1_block = f"""
L1（昨日摘要）：
  昨日主題：{l1['yesterday_headline']}
  昨日術語：{l1['yesterday_term']}
  昨日行動建議：{l1['yesterday_action']}
"""

    l2_block = f"\nL2（本週市場結構）：\n{l2}\n" if l2 else ""

    l3_block = ""
    if l3:
        l3_block = "\nL3（現有 Active Thesis）：\n"
        for t in l3:
            l3_block += f"  - {t['name']}: {t['statement']} (confidence={t.get('confidence', '?')}, invalidators={t.get('invalidators', [])})\n"

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

允許覆蓋推薦框架，但必須說明：「今日框架：[名稱]，理由：[一句話]」。
{l1_block}{l2_block}{l3_block}{kh_block}

今日邊陲地區：{periphery_label}
邊陲搜尋關鍵字：{periphery_keywords}
→ 請用 Grounding 搜尋這個地區的最新動態，寫入邊陲段落。

══════════════════════════════════════════════════
請產出以下結構化草稿（繁體中文）：

## 1. 今天最重要的一件事
一句話概括。不是「市場漲跌多少」，而是「值得知道的一件事」。

## 2. 完整因果鏈
用「因為...所以...」的邏輯串連。每個「所以」之前都說清楚「為什麼」。
包含今天用到的框架名稱。

## 3. 誰受影響
分三類分析：
- 持有股票的人（例如台積電這類半導體股、蘋果這類科技股）
- 持有債券或定存的人
- 持有外幣（美元、其他）的人
每類標記：🔴需要關注 / 🟡保持觀察 / 🟢目前穩定

## 4. 結構化攻擊（執行其中一項）
選擇以下之一執行：
- regime_misclassification: 替代 regime 解讀 + 機率估計
- second_order_inversion: 因果鏈反轉的具體條件
（可選：reflexivity_break 或 omitted_variable_bias）

攻擊結果格式：
- 攻擊類型：[名稱]
- 攻擊內容：[具體論述]
- 反面訊號：如果[條件]發生，今天的判斷可能需要改變

## 5. 今日術語建議
建議 Narrator 解釋哪個術語。要求：
- 不在 KH 已用列表中
- 今天的分析中有用到
- 可以用日常比喻解釋

## 6. 邊陲段落：{periphery_label}
用 Grounding 搜尋最新動態，寫出：
- 這個地方在哪、大概多少人
- 正在發生什麼具體的事
- 跟今天市場有沒有關係

## 7. Thesis 更新
- 現有 thesis 中需要更新的（新 confidence 或 status 變更）
- 如果有新 thesis（每日最多 2 個，active 上限 5 個）：
  {{
    "name": "...",
    "statement": "...",
    "assets": [...],
    "invalidators": [...],
    "measurable_outcome": "含數字和時間",
    "time_horizon": "1w | 2w | 1m",
    "confidence": 0.XX,
    "status": "active"
  }}

## 8. L2 更新建議
提供今天的 micro-format：
regime: [枚舉值]
driver: [今日最主要推動力]
policy: [央行偏向]
fragility: [最需要關注的風險點]
"""


def run_analyst(prompt: str) -> str:
    """呼叫 Gemini 3.1 Pro Preview 執行分析。"""
    logger.info("Running Analyst (Gemini 3.1 Pro Preview)...")

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

        # 提取文字（跳過 thinking parts）
        text_parts = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                if not hasattr(part, "thought") or not part.thought:
                    text_parts.append(part.text)

        result = "\n".join(text_parts)
        logger.info(f"Analyst output: {len(result)} chars")
        return result

    except Exception as e:
        logger.error(f"Analyst error: {e}")
        raise
