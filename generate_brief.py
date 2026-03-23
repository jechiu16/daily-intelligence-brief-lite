"""
Daily Intelligence Brief Generator — v3
Features:
  - 3-layer memory (yesterday full / this-week compressed / long-term tracker)
  - 4 fixed web searches (assets / macro / geopolitics / rotating periphery)
  - Political economy lens woven into every signal
  - Knowledge Desk: one finance + one poli-econ concept
  - Footer: 5 sources, no disclaimer
"""

import os
import re
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
WEEKDAY   = TODAY.weekday()   # 0=Monday
IS_MONDAY = WEEKDAY == 0
DATE_STR  = TODAY.strftime("%Y-%m-%d")
DATE_LABEL = TODAY.strftime("%Y年%m月%d日（%A）").replace(
    "Monday","週一").replace("Tuesday","週二").replace("Wednesday","週三").replace(
    "Thursday","週四").replace("Friday","週五").replace("Saturday","週六").replace("Sunday","週日")

# Periphery rotation: Monday=West Africa, Tue=SE Asia, Wed=Middle East fringe,
#                     Thu=Latin America, Fri=Central Asia
PERIPHERY_SCHEDULE = {
    0: ("西非 + 薩赫勒地區",       "West Africa Sahel security politics 2026"),
    1: ("東南亞 + 湄公河流域",     "Southeast Asia Mekong geopolitics economy 2026"),
    2: ("中東邊陲（葉門、伊拉克、黎巴嫩）", "Yemen Iraq Lebanon conflict politics 2026"),
    3: ("拉丁美洲（委內瑞拉、阿根廷、厄瓜多）", "Venezuela Argentina Ecuador crisis 2026"),
    4: ("中亞 + 高加索",           "Central Asia Caucasus geopolitics 2026"),
}
PERIPHERY_LABEL, PERIPHERY_QUERY = PERIPHERY_SCHEDULE.get(WEEKDAY, PERIPHERY_SCHEDULE[0])

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
TIMEOUT = httpx.Timeout(60.0, connect=10.0)  # 60s read, 10s connect

# ── Prompts ───────────────────────────────────────────────────────────────────
DAILY_SYSTEM = """你是一名服務於全球宏觀對沖基金的策略分析師，同時具備政治學與政治經濟學的深厚背景。

核心任務：提供可用於判斷、配置、避險的高密度資訊與推演。不是整理新聞，是轉譯因果。

分析框架：每個訊號必須同時包含：
- 權力結構視角：誰得利 / 誰受損 / 制度性後果
- 市場定價視角：資產影響 / 風險定價 / 結構變化
- So what? 的明確判斷

你今天會進行4次 web_search，搜尋順序與查詢詞已在 user prompt 中指定，請嚴格遵守，不要額外增加搜尋次數。

格式規則：
- 禁止使用 Markdown 表格，改用 bullet points
- 禁止使用 emoji
- 禁止使用「List」、「列表」等佔位文字，bullet point 直接寫內容
- 可使用標題（#, ##）、粗體（**文字**）、bullet points（- 開頭）
- 每個段落之間空一行，保持閱讀節奏
- 風格：極度理性、冷靜、去情緒化、使用因果鏈
- 語言：繁體中文，保留關鍵英文專業術語
- 結尾列出本報告引用的最重要5個來源（格式：機構 — 標題/類型，日期）
- 禁止在報告開頭說明你要做什麼（如「I'll execute the searches」），直接輸出報告內容"""


def build_daily_prompt(layer1: str, layer2: str, layer3: str) -> str:
    # Build context section from available memory layers
    ctx = ""
    if layer1:
        ctx += f"\n### Layer 1：昨日報告摘要（{YESTERDAY.strftime('%Y-%m-%d')}）\n{layer1}\n"
    if layer2:
        ctx += f"\n### Layer 2：本週每日核心判斷壓縮\n{layer2}\n"
    if layer3:
        ctx += f"\n### Layer 3：長期追蹤清單（持續更新中）\n{layer3}\n"
    if ctx:
        ctx = f"\n## 歷史連貫性背景\n{ctx}\n---\n"

    return f"""請為 {DATE_LABEL} 生成「Daily Intelligence Brief」。

請依序執行以下 4 次 web_search，不多不少：
1. "market snapshot {DATE_STR} SPX bonds oil gold DXY"
2. "macro economic data central bank {DATE_STR}"
3. "geopolitics major events {DATE_STR}"
4. "{PERIPHERY_QUERY}"
{ctx}
生成報告，結構如下：

# Daily Intelligence Brief
{DATE_LABEL} | Strategy & Political Economy Desk

## 今日世界切面
一段話：今天全球最重要的張力在哪個維度。不是新聞摘要，是分析框架的入口。

## 核心宏觀訊號
3個訊號，每個結構：
**訊號名稱**
- 事實（附數據）
- 誰得利 / 誰受損 / 制度性後果
- **So what?**：資產影響 → 操作含義

## 跨資產含義
用 bullet points 列出：美股、固定收益、外匯、大宗商品、黃金。
每條說明背後的政治經濟驅動因素，不只列數字。

## Deep Dive
1-2個值得深挖的主題，輪替選擇：
- 經濟機制（Fed、流動性、信用週期）
- 政治經濟學（選舉、資源控制、制度變遷）
- 地緣分析（權力轉移、同盟重組）
有料才寫，不強迫填滿。

## 地緣構造
條件觸發，非每日固定。只在有實質地理政治變化時出現：
邊界爭議、勢力範圍重劃、港口航道戰略意義、核升級門檻位移等。

## 邊陲世界：{PERIPHERY_LABEL}
基於第4次搜尋結果，分析：
- 當前權力結構與主要行為者
- 地理邏輯（為何這裡是衝突/競爭的節點）
- 與全球宏觀的隱性連結（礦產、航道、移民、代理戰爭）
- 中期演變方向

## Risk Map
5大核心風險，格式：
- **風險名稱**（顏色：紅/橙/黃）：觸發條件 → 資產影響

## 今日思考題
一個開放性問題，無標準答案。
若昨日有思考題，先用一句話回應其進展，再提出今日新題。

---

## Knowledge Desk

### 概念一（金融機制）：[從今日報告萃取]
**為什麼今天重要**（一句話連結今日報告）
**實戰應用邏輯**
- 交易/配置中如何影響決策？
- 什麼條件下會失效？
- 典型錯誤理解是什麼？
**歷史案例**（一個，附年份與結果）
**當前市場的關鍵問題**

### 概念二（政治經濟學）：[從今日報告萃取]
（相同結構）

---

**資料來源**
（列出本報告引用的最重要5個來源，格式：機構 — 標題/類型，日期）"""


LAYER_UPDATE_SYSTEM = """你是一名宏觀對沖基金的資料管理分析師。
任務：根據今日報告，更新兩份持續維護的文件。
語言：繁體中文。格式：bullet points，極度精簡，不要廢話。"""

def build_layer_update_prompt(daily_content: str, old_layer2: str, old_layer3: str) -> str:
    return f"""今日報告內容：
{daily_content[:3000]}

---
現有 Layer 2（本週每日壓縮，最多保留7天）：
{old_layer2 or '（空）'}

現有 Layer 3（長期追蹤清單）：
{old_layer3 or '（空）'}

請輸出以下兩個區塊，用 [LAYER2] 和 [LAYER3] 標記分隔：

[LAYER2]
在現有 Layer 2 末尾加入今日（{DATE_STR}）的壓縮版本。
格式：
{DATE_STR}：
- 核心訊號1（一句話）
- 核心訊號2（一句話）
- 核心訊號3（一句話）
- 主要風險（一句話）
若已超過7天的條目，刪除最舊的。

[LAYER3]
更新長期追蹤清單。規則：
- 只保留跨週仍有追蹤價值的結構性判斷
- 每條一句話，附首次出現日期
- 若某條判斷已兌現或失效，刪除並用一句話記錄結果
- 總長度不超過500字"""


KNOWLEDGE_SYSTEM = """你是一名宏觀對沖基金的資深策略師兼研究導師。
讀者已熟悉基礎概念，需要實戰層的應用角度。
語言：繁體中文，保留關鍵英文術語。每個概念300字以內。"""

WEEKLY_SYSTEM = """你是一名服務於全球宏觀對沖基金的資深策略師，負責週度總結。
語言：繁體中文，保留關鍵英文術語。
格式：禁止表格，使用 bullet points。"""

def build_weekly_prompt(daily_reports: list[dict]) -> str:
    reports_text = "\n\n---\n\n".join(
        f"### {r['date']}\n{r['content']}" for r in daily_reports
    )
    week_start = (TODAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    return f"""以下是上週（{week_start} 至 {DATE_STR}）的每日報告：

{reports_text}

生成週度回顧：

# Weekly Intelligence Review
{week_start} ~ {DATE_STR} | Strategy & Political Economy Desk

## 本週核心主題
3-5個貫穿全週的主線敘事，說明其演進軌跡。

## 跨資產表現回顧
各資產類別本週關鍵走勢與驅動因素，用 bullet points。

## 預測 vs 實際
回顧本週日報的核心判斷：哪些兌現、哪些偏離、原因是什麼。

## 思考題追蹤
本週每日思考題的集體回顧：哪些問題得到了答案，哪些仍在演變。

## 結構性變化追蹤
持續進行中的長期結構性轉變，本週有何進展。

## 下週關鍵觀察點
最重要的5個 catalysts，用 bullet points。

## 週度 Meta Insight
本週最重要的一個洞見，一段話，不超過150字。

---
**資料來源**
（列出本週報告引用的最重要5個來源）"""


# ── Claude API ────────────────────────────────────────────────────────────────
def call_claude_with_search(system: str, user: str) -> str:
    """Agentic loop with web_search tool. Runs until stop_reason == end_turn."""
    client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": user}]

    while True:
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


def call_claude(system: str, user: str, max_tokens: int = 4096) -> str:
    """Standard Claude call without tools."""
    client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return message.content[0].text


# ── Notion rich_text helpers ──────────────────────────────────────────────────
def clean_md(md: str) -> str:
    """
    Pre-process markdown before converting to Notion blocks.
    - Remove bare 'List' / '- List' placeholder lines Claude sometimes emits
    - Normalize bullet markers to '- '
    - Strip trailing whitespace per line
    """
    lines = []
    for line in md.split("\n"):
        stripped = line.strip()
        # Drop bare placeholder lines: '- List', '* List', 'List', '- list' etc.
        if re.match(r'^[-*]?\s*[Ll]ist\s*$', stripped):
            continue
        # Normalize '* ' bullets to '- '
        if line.startswith("* "):
            line = "- " + line[2:]
        lines.append(line.rstrip())
    return "\n".join(lines)


def parse_inline(text: str) -> list:
    """Convert inline markdown (**bold**, *italic*) to Notion rich_text array."""
    rich = []
    # Match **bold**, *italic*, or plain text segments
    pattern = re.compile(r'\*\*(.+?)\*\*|\*(.+?)\*|([^*]+)', re.DOTALL)
    for m in pattern.finditer(text):
        bold_t, italic_t, plain_t = m.group(1), m.group(2), m.group(3)
        if bold_t:
            seg_content, ann = bold_t, {"bold": True}
        elif italic_t:
            seg_content, ann = italic_t, {"italic": True}
        else:
            seg_content, ann = plain_t, {}
        # Notion rich_text items max 2000 chars
        for i in range(0, max(1, len(seg_content)), 2000):
            chunk = seg_content[i:i+2000]
            if not chunk:
                continue
            rt = {"type": "text", "text": {"content": chunk}}
            if ann:
                rt["annotations"] = ann
            rich.append(rt)
    return rich or [{"type": "text", "text": {"content": ""}}]


def md_block(btype: str, rich: list) -> dict:
    """Helper: build a Notion block dict."""
    return {"object": "block", "type": btype, btype: {"rich_text": rich}}


def markdown_to_notion_blocks(md: str) -> list:
    """
    Convert a markdown string to a list of Notion block dicts.
    Handles: h1/h2/h3, bullet lists, numbered lists, dividers, paragraphs.
    Tables are converted to bullet points.
    All 'List' placeholder lines are removed before processing.
    """
    md = clean_md(md)
    blocks = []

    for line in md.split("\n"):
        # ── Headings ──────────────────────────────────────────────────────────
        if line.startswith("# "):
            blocks.append(md_block("heading_1", parse_inline(line[2:].strip())))
        elif line.startswith("## "):
            blocks.append(md_block("heading_2", parse_inline(line[3:].strip())))
        elif line.startswith("### "):
            blocks.append(md_block("heading_3", parse_inline(line[4:].strip())))

        # ── Divider ───────────────────────────────────────────────────────────
        elif re.match(r"^-{3,}$", line.strip()):
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        # ── Bullet list ───────────────────────────────────────────────────────
        elif line.startswith("- "):
            text = line[2:].strip()
            if text:  # skip if content is empty after stripping
                blocks.append(md_block("bulleted_list_item", parse_inline(text)))

        # ── Numbered list ─────────────────────────────────────────────────────
        elif re.match(r"^\d+\.\s", line):
            text = re.sub(r"^\d+\.\s+", "", line).strip()
            if text:
                blocks.append(md_block("numbered_list_item", parse_inline(text)))

        # ── Table row → bullet ────────────────────────────────────────────────
        elif line.strip().startswith("|") and line.strip().endswith("|"):
            # Skip separator rows like |---|---|
            if re.match(r"^[\|\s\-:]+$", line.strip()):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|") if c.strip()]
            if cells:
                blocks.append(md_block("bulleted_list_item", parse_inline(" | ".join(cells))))

        # ── Skip blank lines ──────────────────────────────────────────────────
        elif not line.strip():
            continue

        # ── Paragraph ─────────────────────────────────────────────────────────
        else:
            text = line.strip()
            if text:
                blocks.append(md_block("paragraph", parse_inline(text)))

    return blocks


# ── Notion page helpers ───────────────────────────────────────────────────────
def create_notion_page(db_id: str, title: str, report_type: str = "daily") -> str:
    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": DATE_STR}},
            "Type": {"select": {"name": report_type.capitalize()}},
        },
    }
    resp = httpx.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()["id"]


def append_blocks(page_id: str, content: str):
    blocks = markdown_to_notion_blocks(content)
    for i in range(0, len(blocks), 100):
        r = httpx.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            json={"children": blocks[i:i+100]}
        , timeout=TIMEOUT)
        r.raise_for_status()


# ── Memory layer helpers ──────────────────────────────────────────────────────
LAYER3_PAGE_TITLE = "__LongTermTracker__"
LAYER2_PAGE_TITLE = "__WeeklyCompressed__"


def _find_or_create_memo_page(title: str) -> str:
    """Find a special memo page by title, or create it."""
    payload = {
        "filter": {"property": "Name", "title": {"equals": title}}
    }
    resp = httpx.post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        headers=NOTION_HEADERS, json=payload
    , timeout=TIMEOUT)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if results:
        return results[0]["id"]
    # Create it
    page_payload = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": DATE_STR}},
            "Type": {"select": {"name": "Memo"}},
        },
    }
    r = httpx.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=page_payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["id"]


def read_memo_page(title: str) -> str:
    """Read all text from a memo page."""
    page_id = _find_or_create_memo_page(title)
    resp = httpx.get(
        f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=200",
        headers=NOTION_HEADERS
    , timeout=TIMEOUT)
    resp.raise_for_status()
    lines = []
    for block in resp.json().get("results", []):
        btype = block.get("type", "")
        rich  = block.get(btype, {}).get("rich_text", [])
        text  = "".join(t.get("plain_text", "") for t in rich)
        if text:
            lines.append(text)
    return "\n".join(lines)


def overwrite_memo_page(title: str, content: str):
    """Delete all blocks on a memo page and write new content."""
    page_id = _find_or_create_memo_page(title)
    # Delete existing blocks
    resp = httpx.get(
        f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100",
        headers=NOTION_HEADERS
    , timeout=TIMEOUT)
    resp.raise_for_status()
    for block in resp.json().get("results", []):
        httpx.delete(
            f"https://api.notion.com/v1/blocks/{block['id']}",
            headers=NOTION_HEADERS
        , timeout=TIMEOUT)
    # Write new content
    append_blocks(page_id, content)


def fetch_yesterday_full() -> str:
    """Fetch yesterday's full daily report (Layer 1)."""
    payload = {
        "filter": {
            "and": [
                {"property": "Date", "date":   {"equals": YESTERDAY.strftime("%Y-%m-%d")}},
                {"property": "Type", "select": {"equals": "Daily"}},
            ]
        }
    }
    resp = httpx.post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        headers=NOTION_HEADERS, json=payload
    , timeout=TIMEOUT)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return ""
    br = httpx.get(
        f"https://api.notion.com/v1/blocks/{results[0]['id']}/children?page_size=200",
        headers=NOTION_HEADERS
    , timeout=TIMEOUT)
    br.raise_for_status()
    lines = []
    for block in br.json().get("results", []):
        btype = block.get("type", "")
        rich  = block.get(btype, {}).get("rich_text", [])
        text  = "".join(t.get("plain_text", "") for t in rich)
        if text:
            lines.append(text)
    full = "\n".join(lines)
    # Cap at 2000 chars to control tokens
    return full[:2000] + "..." if len(full) > 2000 else full


def fetch_last_week_reports() -> list[dict]:
    week_ago  = (TODAY - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    yesterday = YESTERDAY.strftime("%Y-%m-%d")
    payload = {
        "filter": {
            "and": [
                {"property": "Date",  "date":   {"on_or_after":  week_ago}},
                {"property": "Date",  "date":   {"on_or_before": yesterday}},
                {"property": "Type",  "select": {"equals": "Daily"}},
            ]
        },
        "sorts": [{"property": "Date", "direction": "ascending"}],
    }
    resp = httpx.post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        headers=NOTION_HEADERS, json=payload
    , timeout=TIMEOUT)
    resp.raise_for_status()
    reports = []
    for page in resp.json().get("results", []):
        date_str = (page["properties"].get("Date", {}).get("date") or {}).get("start", "")
        br = httpx.get(
            f"https://api.notion.com/v1/blocks/{page['id']}/children?page_size=200",
            headers=NOTION_HEADERS
        , timeout=TIMEOUT)
        br.raise_for_status()
        lines = []
        for block in br.json().get("results", []):
            btype = block.get("type", "")
            rich  = block.get(btype, {}).get("rich_text", [])
            text  = "".join(t.get("plain_text", "") for t in rich)
            if text:
                lines.append(text)
        if lines:
            reports.append({"date": date_str, "content": "\n".join(lines)})
    return reports


def parse_layer_update(raw: str) -> tuple[str, str]:
    """Extract [LAYER2] and [LAYER3] sections from Claude's update response."""
    layer2, layer3 = "", ""
    if "[LAYER2]" in raw and "[LAYER3]" in raw:
        parts = raw.split("[LAYER3]")
        layer3 = parts[1].strip()
        layer2 = parts[0].replace("[LAYER2]", "").strip()
    elif "[LAYER2]" in raw:
        layer2 = raw.replace("[LAYER2]", "").strip()
    elif "[LAYER3]" in raw:
        layer3 = raw.replace("[LAYER3]", "").strip()
    return layer2, layer3


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{DATE_STR}] Starting Daily Intelligence Brief (v3)...")

    # ── Load memory layers ──────────────────────────────────────────────────
    print("  → Loading memory layers...")
    layer1 = fetch_yesterday_full()
    layer2 = read_memo_page(LAYER2_PAGE_TITLE)
    layer3 = read_memo_page(LAYER3_PAGE_TITLE)
    print(f"    L1: {'loaded' if layer1 else 'empty'}  "
          f"L2: {'loaded' if layer2 else 'empty'}  "
          f"L3: {'loaded' if layer3 else 'empty'}")

    # ── Generate daily report (4 fixed searches) ────────────────────────────
    print(f"  → Generating report (periphery: {PERIPHERY_LABEL})...")
    daily_prompt   = build_daily_prompt(layer1, layer2, layer3)
    daily_content  = call_claude_with_search(DAILY_SYSTEM, daily_prompt)
    print("  ✓ Report generated")

    # ── Update memory layers ────────────────────────────────────────────────
    print("  → Updating memory layers...")
    update_raw     = call_claude(
        LAYER_UPDATE_SYSTEM,
        build_layer_update_prompt(daily_content, layer2, layer3),
        max_tokens=2000
    )
    new_layer2, new_layer3 = parse_layer_update(update_raw)
    if new_layer2:
        overwrite_memo_page(LAYER2_PAGE_TITLE, new_layer2)
    if new_layer3:
        overwrite_memo_page(LAYER3_PAGE_TITLE, new_layer3)
    print("  ✓ Memory layers updated")

    # ── Push to Notion ──────────────────────────────────────────────────────
    page_id = create_notion_page(NOTION_DB_ID, f"📊 Daily Brief | {DATE_STR}", "daily")
    append_blocks(page_id, daily_content)
    print(f"  ✓ Daily brief pushed to Notion (page: {page_id})")

    # ── Weekly review on Mondays ────────────────────────────────────────────
    if IS_MONDAY:
        print("  → Monday: generating weekly review...")
        weekly_reports = fetch_last_week_reports()
        if weekly_reports:
            weekly_content = call_claude(
                WEEKLY_SYSTEM,
                build_weekly_prompt(weekly_reports),
                max_tokens=5000
            )
            week_start = (TODAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            w_id = create_notion_page(
                NOTION_WEEKLY_DB,
                f"📅 Weekly Review | {week_start} ~ {DATE_STR}",
                "weekly"
            )
            append_blocks(w_id, weekly_content)
            print(f"  ✓ Weekly review pushed (page: {w_id})")
        else:
            print("  ⚠ No daily reports found — skipping weekly review.")

    print("Done.")


if __name__ == "__main__":
    main()
