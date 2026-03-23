"""
Daily Intelligence Brief Generator — v4
Changes from v3:
  - Full error handling with retry logic on all API calls
  - Safe memory layer update (write-then-delete, not delete-then-write)
  - JSON-based layer parsing (no brittle string splitting)
  - Correct execution order (push Notion first, update memory after)
  - Knowledge Desk as separate Claude call (cost control + stability)
  - Weekly review uses Layer 2 compressed summaries, not full reports
  - Deduplicated Notion read logic into single helper
  - search loop hard-capped at 8 iterations
  - Unified timeout handling
"""

import os
import re
import json
import time
import datetime
import anthropic
import httpx

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY    = os.environ["NOTION_API_KEY"]
NOTION_DB_ID      = os.environ["NOTION_DATABASE_ID"]
NOTION_WEEKLY_DB  = os.environ.get("NOTION_WEEKLY_DB_ID", NOTION_DB_ID)

TODAY     = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)
WEEKDAY   = TODAY.weekday()
IS_MONDAY = WEEKDAY == 0
DATE_STR  = TODAY.strftime("%Y-%m-%d")
DATE_LABEL = TODAY.strftime("%Y年%m月%d日（%A）").replace(
    "Monday","週一").replace("Tuesday","週二").replace("Wednesday","週三").replace(
    "Thursday","週四").replace("Friday","週五").replace("Saturday","週六").replace("Sunday","週日")

PERIPHERY_SCHEDULE = {
    0: ("西非 + 薩赫勒地區",                  "West Africa Sahel security politics 2026"),
    1: ("東南亞 + 湄公河流域",                "Southeast Asia Mekong geopolitics economy 2026"),
    2: ("中東邊陲（葉門、伊拉克、黎巴嫩）",  "Yemen Iraq Lebanon conflict politics 2026"),
    3: ("拉丁美洲（委內瑞拉、阿根廷、厄瓜多）","Venezuela Argentina Ecuador crisis 2026"),
    4: ("中亞 + 高加索",                       "Central Asia Caucasus geopolitics 2026"),
}
PERIPHERY_LABEL, PERIPHERY_QUERY = PERIPHERY_SCHEDULE.get(WEEKDAY, PERIPHERY_SCHEDULE[0])

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
TIMEOUT        = httpx.Timeout(60.0, connect=10.0)
MAX_RETRIES    = 3
RETRY_DELAY    = 5   # seconds

LAYER2_TITLE   = "__WeeklyCompressed__"
LAYER3_TITLE   = "__LongTermTracker__"

# ── Retry helper ──────────────────────────────────────────────────────────────
def with_retry(fn, *args, retries=MAX_RETRIES, delay=RETRY_DELAY, **kwargs):
    """Call fn(*args, **kwargs), retrying up to `retries` times on exception."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            print(f"    ⚠ Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"All {retries} attempts failed") from last_exc

# ── Prompts ───────────────────────────────────────────────────────────────────
DAILY_SYSTEM = """你是一名服務於全球宏觀對沖基金的策略分析師，同時具備政治學與政治經濟學的深厚背景。

核心任務：提供可用於判斷、配置、避險的高密度資訊與推演。不是整理新聞，是轉譯因果。

分析框架：每個訊號必須同時包含：
- 權力結構視角：誰得利 / 誰受損 / 制度性後果
- 市場定價視角：資產影響 / 風險定價 / 結構變化
- So what? 的明確判斷

你今天會進行4次 web_search，搜尋順序與查詢詞已在 user prompt 中指定，請嚴格遵守，不要額外增加搜尋次數。

格式規則（嚴格遵守）：
- 語言：繁體中文，保留關鍵英文專業術語
- 禁止使用 Markdown 表格
- 禁止使用 emoji
- 禁止使用「List」「列表」等佔位文字
- 禁止在報告開頭說明你要做什麼，直接輸出報告內容
- 標題用 ## ，子標題用 ###
- bullet points 用 - 開頭，每條至少一句完整的話
- 段落（非 bullet）寫成 2-3 句連貫的話，不要每句話獨立換行
- 風格：極度理性、冷靜、去情緒化、使用因果鏈"""


def build_daily_prompt(layer1: str, layer2: str, layer3: str) -> str:
    ctx = ""
    if layer1:
        ctx += f"\n### 昨日報告摘要（{YESTERDAY.strftime('%Y-%m-%d')}）\n{layer1}\n"
    if layer2:
        ctx += f"\n### 本週每日核心判斷\n{layer2}\n"
    if layer3:
        ctx += f"\n### 長期追蹤清單\n{layer3}\n"
    if ctx:
        ctx = f"\n---\n## 歷史連貫性背景\n{ctx}\n---\n"

    return f"""請為 {DATE_LABEL} 生成「Daily Intelligence Brief」。

請依序執行以下 4 次 web_search，不多不少：
1. "market snapshot {DATE_STR} SPX bonds oil gold DXY"
2. "macro economic data central bank {DATE_STR}"
3. "geopolitics major events {DATE_STR}"
4. "{PERIPHERY_QUERY}"
{ctx}
# Daily Intelligence Brief
{DATE_LABEL} | Strategy & Political Economy Desk

## 今日世界切面
一段話：今天全球最重要的張力在哪個維度。不是新聞摘要，是分析框架的入口。

## 核心宏觀訊號
3個訊號，每個結構：
**訊號名稱**
事實段落（附數據，2-3句連貫的話）
- 誰得利 / 誰受損 / 制度性後果
- **So what?**：資產影響 → 操作含義

## 跨資產含義
- **美股**：走勢 + 政治經濟驅動因素
- **固定收益**：殖利率動態 + 原因
- **外匯**：DXY 及主要貨幣對
- **大宗商品**：原油、銅、農產品
- **黃金**：避險需求與定價邏輯

## Deep Dive
1個值得深挖的主題（經濟機制 / 政治經濟學 / 地緣分析，三者輪替）。
用 3-4 段連貫段落說明機制，不要拆成 bullet points。

## 地緣構造
只在有實質地緣政治變化時出現（邊界爭議、勢力範圍重劃、核升級門檻位移）。
若今日無實質變化，省略此章節。

## 邊陲世界：{PERIPHERY_LABEL}
基於第4次搜尋，用 3-4 段連貫段落分析：當前權力結構、地理邏輯、與全球宏觀的隱性連結、中期演變方向。

## Risk Map
- **風險一**（🔴紅）：觸發條件 → 資產影響
- **風險二**（🟠橙）：觸發條件 → 資產影響
- **風險三**（🟠橙）：觸發條件 → 資產影響
- **風險四**（🟡黃）：觸發條件 → 資產影響
- **風險五**（🟡黃）：觸發條件 → 資產影響

## 今日思考題
若昨日有思考題，先一句話回應其進展。
然後提出今日新問題（開放性，無標準答案）。

---

**資料來源**
1. 機構 — 標題，日期
2. 機構 — 標題，日期
3. 機構 — 標題，日期
4. 機構 — 標題，日期
5. 機構 — 標題，日期"""


KNOWLEDGE_SYSTEM = """你是一名宏觀對沖基金的資深策略師兼研究導師。
讀者是政治學背景、志在金融的學生，已熟悉基礎概念，需要實戰層的應用角度。
語言：繁體中文，保留關鍵英文術語。
每個概念嚴格控制在 200 字以內，精準不囉嗦。"""


def build_knowledge_prompt(report_content: str) -> str:
    return f"""以下是今日的宏觀報告（節錄）：

{report_content[:2000]}

從報告中萃取 2 個「值得實戰層深挖」的概念，一個金融機制、一個政治經濟學概念。

選擇標準：對理解今日市場邏輯至關重要，但「知道原理、不確定怎麼用」的概念。

每個概念輸出格式（嚴格遵守，各200字以內）：

### 概念：[名稱]
**為什麼今天重要**：一句話連結今日報告。
**實戰應用**：在交易或配置中如何影響決策？什麼條件下會失效？典型錯誤理解是什麼？
**歷史案例**：一個真實案例，附年份與結果。
**當前關鍵問題**：基於今日環境，最值得追蹤的一個問題。"""


LAYER_UPDATE_SYSTEM = """你是一名宏觀對沖基金的資料管理分析師。
輸出必須是合法的 JSON，不要加任何說明文字或 markdown 代碼塊。"""


def build_layer_update_prompt(report_summary: str, old_layer2: str, old_layer3: str) -> str:
    return f"""根據今日報告摘要，更新記憶層。輸出純 JSON，格式如下：

{{
  "layer2": "更新後的完整 Layer 2 文字",
  "layer3": "更新後的完整 Layer 3 文字"
}}

今日報告摘要（{DATE_STR}）：
{report_summary}

現有 Layer 2（本週每日壓縮，保留最近7天）：
{old_layer2 or "（空）"}

現有 Layer 3（長期追蹤清單）：
{old_layer3 or "（空）"}

Layer 2 規則：在末尾加入今日條目，格式：
{DATE_STR}：核心訊號1 / 核心訊號2 / 核心訊號3 / 主要風險
超過7天的條目刪除。

Layer 3 規則：只保留跨週仍有價值的結構性判斷，每條一句話附日期，總長不超過400字。已兌現或失效的條目刪除。"""


WEEKLY_SYSTEM = """你是一名服務於全球宏觀對沖基金的資深策略師，負責週度總結。
語言：繁體中文，保留關鍵英文術語。
格式：禁止表格，段落為主，必要時用 bullet points。"""


def build_weekly_prompt(layer2: str, layer3: str) -> str:
    week_start = (TODAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    return f"""以下是本週每日核心判斷的壓縮摘要：

{layer2 or "（本週尚無記錄）"}

長期追蹤清單：
{layer3 or "（空）"}

生成週度回顧：

# Weekly Intelligence Review
{week_start} ~ {DATE_STR} | Strategy & Political Economy Desk

## 本週核心主題
3-5個貫穿全週的主線敘事，說明演進軌跡，用段落寫，不用 bullet。

## 跨資產表現回顧
各資產類別本週關鍵走勢與驅動因素。

## 預測 vs 實際
回顧本週核心判斷：哪些兌現、哪些偏離、原因是什麼。

## 思考題追蹤
本週思考題的集體回顧：哪些得到答案，哪些仍在演變。

## 結構性變化追蹤
長期追蹤清單中，本週有何進展或需要更新的判斷。

## 下週關鍵觀察點
- 最重要的5個 catalysts 或數據點

## 週度 Meta Insight
本週最重要的一個洞見，一段話，不超過150字。

---
**資料來源**
（本週報告引用的最重要5個來源）"""


# ── Claude API ────────────────────────────────────────────────────────────────
def call_claude_with_search(system: str, user: str) -> str:
    """Agentic loop with web_search. Hard cap at 8 iterations."""
    client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": user}]
    MAX_ITER = 8

    for _ in range(MAX_ITER):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            system=system,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]

        if response.stop_reason == "end_turn":
            return "\n".join(text_blocks)

        messages.append({"role": "assistant", "content": response.content})
        tool_results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": "Search executed."}
            for b in response.content if b.type == "tool_use"
        ]
        if not tool_results:
            return "\n".join(text_blocks)
        messages.append({"role": "user", "content": tool_results})

    # Safety fallback
    return "\n".join([b.text for b in response.content if hasattr(b, "text")])


def call_claude(system: str, user: str, max_tokens: int = 2000) -> str:
    client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return message.content[0].text


# ── Markdown → Notion blocks ──────────────────────────────────────────────────
def clean_md(md: str) -> str:
    lines = []
    for line in md.split("\n"):
        stripped = line.strip()
        if re.match(r"^[-*]?\s*[Ll]ist\s*$", stripped):
            continue
        if re.match(r"^[-*]\s*$", stripped):
            continue
        if line.startswith("* "):
            line = "- " + line[2:]
        lines.append(line.rstrip())
    return "\n".join(lines)


def parse_inline(text: str) -> list:
    rich    = []
    pattern = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*|([^*]+)", re.DOTALL)
    for m in pattern.finditer(text):
        bold_t, italic_t, plain_t = m.group(1), m.group(2), m.group(3)
        if bold_t:
            seg, ann = bold_t, {"bold": True}
        elif italic_t:
            seg, ann = italic_t, {"italic": True}
        else:
            seg, ann = plain_t, {}
        for i in range(0, max(1, len(seg)), 2000):
            chunk = seg[i:i+2000]
            if not chunk:
                continue
            rt = {"type": "text", "text": {"content": chunk}}
            if ann:
                rt["annotations"] = ann
            rich.append(rt)
    return rich or [{"type": "text", "text": {"content": ""}}]


def mk(btype: str, rich: list) -> dict:
    return {"object": "block", "type": btype, btype: {"rich_text": rich}}


def markdown_to_notion_blocks(md: str) -> list:
    md     = clean_md(md)
    blocks = []
    for line in md.split("\n"):
        if line.startswith("# "):
            blocks.append(mk("heading_1", parse_inline(line[2:].strip())))
        elif line.startswith("## "):
            blocks.append(mk("heading_2", parse_inline(line[3:].strip())))
        elif line.startswith("### "):
            blocks.append(mk("heading_3", parse_inline(line[4:].strip())))
        elif re.match(r"^-{3,}$", line.strip()):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif line.startswith("- "):
            text = line[2:].strip()
            if text:
                blocks.append(mk("bulleted_list_item", parse_inline(text)))
        elif re.match(r"^\d+\.\s", line):
            text = re.sub(r"^\d+\.\s+", "", line).strip()
            if text:
                blocks.append(mk("numbered_list_item", parse_inline(text)))
        elif line.strip().startswith("|") and line.strip().endswith("|"):
            if re.match(r"^[\|\s\-:]+$", line.strip()):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|") if c.strip()]
            if cells:
                blocks.append(mk("bulleted_list_item", parse_inline(" | ".join(cells))))
        elif line.strip():
            blocks.append(mk("paragraph", parse_inline(line.strip())))
    return blocks


# ── Notion helpers ────────────────────────────────────────────────────────────
def notion_post(url: str, payload: dict) -> dict:
    resp = with_retry(
        httpx.post, url, headers=NOTION_HEADERS, json=payload, timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def notion_patch(url: str, payload: dict) -> dict:
    resp = with_retry(
        httpx.patch, url, headers=NOTION_HEADERS, json=payload, timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def notion_get(url: str) -> dict:
    resp = with_retry(
        httpx.get, url, headers=NOTION_HEADERS, timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def notion_delete(url: str):
    with_retry(httpx.delete, url, headers=NOTION_HEADERS, timeout=TIMEOUT)


def read_page_content(page_id: str, page_size: int = 200) -> str:
    """Fetch all text from a Notion page's blocks."""
    data  = notion_get(f"https://api.notion.com/v1/blocks/{page_id}/children?page_size={page_size}")
    lines = []
    for block in data.get("results", []):
        btype = block.get("type", "")
        rich  = block.get(btype, {}).get("rich_text", [])
        text  = "".join(t.get("plain_text", "") for t in rich)
        if text:
            lines.append(text)
    return "\n".join(lines)


def append_blocks(page_id: str, content: str):
    blocks = markdown_to_notion_blocks(content)
    for i in range(0, len(blocks), 100):
        notion_patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            {"children": blocks[i:i+100]}
        )


def create_page(db_id: str, title: str, report_type: str) -> str:
    data = notion_post("https://api.notion.com/v1/pages", {
        "parent": {"database_id": db_id},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": DATE_STR}},
            "Type": {"select": {"name": report_type.capitalize()}},
        },
    })
    return data["id"]


def find_or_create_memo(title: str) -> str:
    data = notion_post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        {"filter": {"property": "Name", "title": {"equals": title}}}
    )
    results = data.get("results", [])
    if results:
        return results[0]["id"]
    data = notion_post("https://api.notion.com/v1/pages", {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": DATE_STR}},
            "Type": {"select": {"name": "Memo"}},
        },
    })
    return data["id"]


def read_memo(title: str) -> str:
    page_id = find_or_create_memo(title)
    return read_page_content(page_id)


def safe_overwrite_memo(title: str, new_content: str):
    """
    Write-then-delete: append new blocks first, then delete old ones.
    Prevents data loss if connection drops mid-operation.
    """
    page_id = find_or_create_memo(title)

    # 1. Read existing block IDs
    data      = notion_get(f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100")
    old_ids   = [b["id"] for b in data.get("results", [])]

    # 2. Write new content
    append_blocks(page_id, new_content)

    # 3. Only now delete old blocks
    for block_id in old_ids:
        try:
            notion_delete(f"https://api.notion.com/v1/blocks/{block_id}")
        except Exception as e:
            print(f"    ⚠ Could not delete old block {block_id}: {e}")


# ── Memory layer fetch ────────────────────────────────────────────────────────
def fetch_layer1() -> str:
    """Yesterday's report: only the first 5 sections (skip Knowledge Desk)."""
    data = notion_post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        {"filter": {"and": [
            {"property": "Date",  "date":   {"equals": YESTERDAY.strftime("%Y-%m-%d")}},
            {"property": "Type",  "select": {"equals": "Daily"}},
        ]}}
    )
    results = data.get("results", [])
    if not results:
        return ""
    content = read_page_content(results[0]["id"])
    # Cap at 1500 chars — enough context without burning tokens
    return content[:1500] + "…" if len(content) > 1500 else content


def fetch_last_week_pages() -> list[dict]:
    """Used only for weekly review — returns page IDs and dates."""
    week_ago  = (TODAY - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    yesterday = YESTERDAY.strftime("%Y-%m-%d")
    data = notion_post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        {
            "filter": {"and": [
                {"property": "Date",  "date":   {"on_or_after":  week_ago}},
                {"property": "Date",  "date":   {"on_or_before": yesterday}},
                {"property": "Type",  "select": {"equals": "Daily"}},
            ]},
            "sorts": [{"property": "Date", "direction": "ascending"}],
        }
    )
    return data.get("results", [])


# ── Layer update parsing ──────────────────────────────────────────────────────
def parse_layer_update(raw: str) -> tuple[str, str]:
    """Parse JSON response from layer update call."""
    raw = raw.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    try:
        data = json.loads(raw)
        return data.get("layer2", ""), data.get("layer3", "")
    except json.JSONDecodeError as e:
        print(f"    ⚠ Layer update JSON parse failed: {e}")
        print(f"    Raw response: {raw[:200]}")
        return "", ""


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{DATE_STR}] Daily Intelligence Brief v4 — {PERIPHERY_LABEL}")

    # ── 1. Load memory layers ─────────────────────────────────────────────────
    print("  → Loading memory layers...")
    try:
        layer1 = fetch_layer1()
        layer2 = read_memo(LAYER2_TITLE)
        layer3 = read_memo(LAYER3_TITLE)
        print(f"    L1={'loaded' if layer1 else 'empty'}  "
              f"L2={'loaded' if layer2 else 'empty'}  "
              f"L3={'loaded' if layer3 else 'empty'}")
    except Exception as e:
        print(f"    ⚠ Memory load failed ({e}), continuing with empty context")
        layer1 = layer2 = layer3 = ""

    # ── 2. Generate daily report ──────────────────────────────────────────────
    print("  → Generating daily report (4 searches)...")
    daily_content = with_retry(
        call_claude_with_search,
        DAILY_SYSTEM,
        build_daily_prompt(layer1, layer2, layer3)
    )
    print("  ✓ Report generated")

    # ── 3. Generate Knowledge Desk (separate call, cost-controlled) ───────────
    print("  → Generating Knowledge Desk...")
    knowledge_content = with_retry(
        call_claude,
        KNOWLEDGE_SYSTEM,
        build_knowledge_prompt(daily_content),
        max_tokens=1500
    )
    print("  ✓ Knowledge Desk generated")

    # ── 4. Push to Notion FIRST ───────────────────────────────────────────────
    print("  → Pushing to Notion...")
    page_id = create_page(NOTION_DB_ID, f"📊 Daily Brief | {DATE_STR}", "daily")
    append_blocks(page_id, daily_content)
    append_blocks(page_id, "\n---\n\n## Knowledge Desk\n")
    append_blocks(page_id, knowledge_content)
    print(f"  ✓ Pushed to Notion (page: {page_id})")

    # ── 5. Update memory layers AFTER successful push ─────────────────────────
    print("  → Updating memory layers...")
    # Build a short summary for layer update (first 1500 chars of report)
    report_summary = daily_content[:1500]
    try:
        update_raw = call_claude(
            LAYER_UPDATE_SYSTEM,
            build_layer_update_prompt(report_summary, layer2, layer3),
            max_tokens=1500
        )
        new_layer2, new_layer3 = parse_layer_update(update_raw)
        if new_layer2:
            safe_overwrite_memo(LAYER2_TITLE, new_layer2)
        if new_layer3:
            safe_overwrite_memo(LAYER3_TITLE, new_layer3)
        print("  ✓ Memory layers updated")
    except Exception as e:
        print(f"  ⚠ Memory update failed ({e}) — report already saved, skipping")

    # ── 6. Weekly review on Mondays ───────────────────────────────────────────
    if IS_MONDAY:
        print("  → Generating weekly review...")
        try:
            # Use Layer 2 compressed summaries instead of full reports
            fresh_layer2 = read_memo(LAYER2_TITLE)
            fresh_layer3 = read_memo(LAYER3_TITLE)
            weekly_content = with_retry(
                call_claude,
                WEEKLY_SYSTEM,
                build_weekly_prompt(fresh_layer2, fresh_layer3),
                max_tokens=4000
            )
            week_start = (TODAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            w_id = create_page(
                NOTION_WEEKLY_DB,
                f"📅 Weekly Review | {week_start} ~ {DATE_STR}",
                "weekly"
            )
            append_blocks(w_id, weekly_content)
            print(f"  ✓ Weekly review pushed (page: {w_id})")
        except Exception as e:
            print(f"  ⚠ Weekly review failed ({e})")

    print("Done.")


if __name__ == "__main__":
    main()
