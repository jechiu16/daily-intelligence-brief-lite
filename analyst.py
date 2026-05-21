"""
analyst.py — Analyst 模組
"""

import logging

from config import GOOGLE_API_KEY, MODEL_ANALYST
from knowledge_terms import format_knowledge_candidates

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
        temperature=0.7,
        max_output_tokens=12000,
        thinking_config=types.ThinkingConfig(
            thinking_budget=12000
        ),
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )

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
    knowledge_candidates=None,
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
    used_terms = []
    if kh:
        used_terms = [item["term"] for item in kh]
        kh_block = f"\nKH（已用過的術語，避免重複）：{', '.join(used_terms)}\n"

    flags_block = ""
    if relational_flags:
        flags_block = "\n⚡ Relational Flags（必須在分析中處理）：\n"
        for f in relational_flags:
            flags_block += f"  {f}\n"

    knowledge_block = format_knowledge_candidates(knowledge_candidates or [])

    return f"""你是 Daily Intelligence Brief 的首席分析師兼選題編輯。
你的任務不是產出一份投資報告，而是為一篇高品質世界日報整理素材：選出今天最值得理解的一條主線，交代市場、政策、地緣或社會變化之間的因果，並保留一個真正邊陲地區的小知識。
這個草稿是給 Narrator（主筆）用的，不是給讀者看的；你可以使用術語，但必須幫主筆判斷哪些術語值得解釋。

{level_a}

{level_b}
{flags_block}

Regime: {regime}
推薦框架: {framework}
{FRAMEWORK_LIBRARY}
{l1_block}{l2_block}{l3_block}{kh_block}

今日一件事候選池（優先從中挑選）：
{knowledge_block}

今日邊陲地區：{periphery_label}
邊陲搜尋關鍵字：{periphery_keywords}
→ 請搜尋這個地區的最新動態，寫入邊陲段落。
→ 邊陲必須真的是邊陲：避開 G7、中國、台灣、華爾街、矽谷、Fed、歐盟核心等主流資訊中心；重點放在小國、邊境、港口、礦區、島嶼、糧食帶、內陸走廊、治理破碎地區。
→ 如果它和今日市場主線沒有直接關係，請坦白說沒有直接關係，再說明它作為世界知識為什麼值得知道；不要硬湊關聯。

══════════════════════════════════════════════════
請產出以下結構化草稿（繁體中文）。
⚠️ 警告：為了系統寫入資料庫，請【嚴格遵守】以下各區塊的標題與格式，切勿擅自更改！

## 1. 今天最重要的一件事
一句話概括今天世界最值得理解的主線。可以來自市場，但不要寫成交易建議。

## 2. 完整因果鏈
用「因為...所以...」邏輯串連。包含框架名稱，但避免堆術語。重點是讓主筆能寫成一篇有節奏的文章。

## 3. 讀者該如何理解
用三點整理這件事對一般讀者理解世界有什麼幫助。
不要假設讀者正在操作股票、債券或外匯；可以提到資產價格，但語氣是解釋世界，不是投資喊單。

## 4. 結構化攻擊 (L4 更新)
選擇 regime_misclassification, second_order_inversion, reflexivity_break, omitted_variable_bias 之一執行。
⚠️ 必須嚴格使用以下格式（不要加 Markdown 粗體星號）：
攻擊類型：[填入上述四種之一]
攻擊內容：[填入具體的邏輯推演與市場盲點，500字以內]
反面訊號：[填入能證明此攻擊成立的市場訊號]

## 5. 今日術語建議 (KH 更新)
挑選一個今天報告中用到、可以用日常比喻解釋的小知識詞彙（絕對不能是已用列表中的詞彙）。
可以是金融術語、地理概念、歷史背景、國際政治詞、航運/能源/糧食常識；不必侷限於投資詞彙。
請優先從「今日一件事候選池」中挑選最貼近今日主線或邊陲的詞。
如果候選池完全不適合，才可以自產一個詞，但必須符合：不太泛、可用三段說清楚、和今日主線或邊陲有明確關係。
⚠️ 必須嚴格使用以下格式：
今日術語：[填入單一名詞]

## 6. 邊陲段落：{periphery_label}
在哪、多少人、最近正在發生什麼、它提醒我們世界哪個被忽略的面向。
如果跟今天市場沒有直接關係，請明確寫「沒有直接關係」，不要硬湊。

## 7. 文章追蹤線索 (L3 更新)
基於今日主線，產出 1~2 個後續值得追蹤的世界觀察線索。
⚠️ 必須嚴格使用 Markdown JSON 陣列格式，且只包含 name 和 statement 欄位，例如：
```json
[
  {{
    "name": "Red_Sea_Routing_Pressure",
    "statement": "如果紅海航運風險持續，歐亞貨運時間與保險成本會成為觀察全球供應鏈壓力的線索。"
  }}
]
```

## 8. L2 更新建議 (市場結構更新)
總結當前的宏觀體制狀態。
⚠️ 必須嚴格使用以下格式逐行輸出（不可使用項目符號、不可加粗體）：
regime: {regime}
driver: [填入主要推動當前市場的因素]
policy: [填入目前貨幣與財政政策狀態]
fragility: [填入當前市場最脆弱的環節]
"""


def run_analyst(prompt):
    logger.info("Running Analyst...")
    try:
        response = _get_client().models.generate_content(
            model=MODEL_ANALYST,
            contents=prompt,
            config=_build_generate_config(),
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
