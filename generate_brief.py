"""
Daily Macro & Geopolitical Intelligence Brief Generator
Calls Claude API → pushes result to Notion
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

TODAY      = datetime.date.today()
WEEKDAY    = TODAY.weekday()
IS_MONDAY  = WEEKDAY == 0
DATE_STR   = TODAY.strftime("%Y-%m-%d")
DATE_LABEL = TODAY.strftime("%Y年%m月%d日（%A）").replace(
    "Monday","週一").replace("Tuesday","週二").replace("Wednesday","週三").replace(
    "Thursday","週四").replace("Friday","週五").replace("Saturday","週六").replace("Sunday","週日")

# ── Prompts ───────────────────────────────────────────────────────────────────
DAILY_SYSTEM = """你是一名服務於全球宏觀對沖基金（Global Macro Hedge Fund）的策略分析師。
你的核心任務不是整理新聞，而是提供可用於判斷、配置、避險的高密度資訊與推演。

所有內容必須回答「So what?」，所有事件需轉譯為：
- 資產影響（Asset Impact）
- 風險定價（Risk Pricing）
- 結構變化（Structural Shift）

格式規則（非常重要）：
- 禁止使用 Markdown 表格（| 欄位 | 格式 |），改用 bullet points 列出
- 禁止使用 emoji
- 可以使用標題（#）、粗體（**文字**）、bullet points（-）
- 風險清單請用 bullet points，格式：- 風險名稱：觸發條件 / 資產影響

風格：極度理性、冷靜、去情緒化、使用因果鏈。
語言：繁體中文，保留關鍵英文專業術語。
重點：總體經濟（利率、通膨、流動性）、地緣政治（權力結構）、政治經濟學（政策→市場）、法治/制度變化。"""

DAILY_USER = f"""請為 {DATE_LABEL} 生成一份「Daily Macro & Geopolitical Intelligence Brief」。

嚴格遵守以下輸出結構：

# Daily Macro & Geopolitical Intelligence Brief
{DATE_LABEL}｜Global Macro Hedge Fund Strategy Desk

## 1. Top Macro Signals
（3-4個最重要的宏觀訊號，每個需包含 So what? 的因果鏈分析）

## 2. Cross-Asset Implications
（跨資產影響：股票、固定收益、外匯、大宗商品、黃金，用 bullet points 列出）

## 3. Deep Dives
（2-3個深度分析，包含機制解讀）

## 4. Under-the-Radar Regions
（被市場忽視但值得注意的地區或主題）

## 5. Risk Map
（5大核心風險，每條用 bullet point，格式：- 風險名稱：觸發條件 / 資產影響）

## 6. Signals to Monitor
（本週關鍵觀察點，用 bullet points 列出）

## 7. Meta Insight
（結構性洞察：本日事件的長期意義）

---
本報告為策略分析參考，不構成投資建議。"""

WEEKLY_SYSTEM = """你是一名服務於全球宏觀對沖基金的資深策略師，負責每週總結回顧。
語言：繁體中文，保留關鍵英文專業術語。
格式規則：禁止使用 Markdown 表格，改用 bullet points。禁止使用 emoji。"""

def build_weekly_prompt(daily_reports: list[dict]) -> str:
    reports_text = "\n\n---\n\n".join(
        f"### {r['date']}\n{r['content']}" for r in daily_reports
    )
    week_start = (TODAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    return f"""以下是上週（{week_start} 至 {DATE_STR}）的每日宏觀報告，請整合並生成週度回顧：

{reports_text}

請用以下結構輸出週報：

# Weekly Macro Review
{week_start} ～ {DATE_STR}｜Global Macro Hedge Fund Strategy Desk

## 本週核心主題
（3-5個貫穿全週的主線敘事，用 bullet points）

## 跨資產表現回顧
（各資產類別本週的關鍵走勢與驅動因素，用 bullet points）

## 預測 vs 實際
（回顧上週預期，哪些兌現、哪些偏離，原因是什麼）

## 結構性變化追蹤
（持續進行中的長期結構性轉變進度更新）

## 下週關鍵觀察點
（下週最重要的5個 catalysts 和數據點，用 bullet points）

## 週度 Meta Insight
（本週最重要的一個洞見）

---
本報告為策略分析參考，不構成投資建議。"""

# ── Notion rich_text builder ──────────────────────────────────────────────────
def parse_inline(text: str) -> list:
    """
    Parse inline markdown into Notion rich_text array.
    Handles: **bold**, *italic*, **bold and *italic* mixed**
    Chunks each segment to ≤ 2000 chars.
    """
    rich = []
    # Pattern matches **bold**, *italic*, or plain text
    pattern = re.compile(r'\*\*(.+?)\*\*|\*(.+?)\*|([^*]+)', re.DOTALL)

    for m in pattern.finditer(text):
        bold_text   = m.group(1)  # **...**
        italic_text = m.group(2)  # *...*
        plain_text  = m.group(3)  # plain

        if bold_text:
            content, annotations = bold_text, {"bold": True}
        elif italic_text:
            content, annotations = italic_text, {"italic": True}
        else:
            content, annotations = plain_text, {}

        # Chunk to ≤ 2000 chars
        for i in range(0, len(content), 2000):
            chunk = content[i:i+2000]
            rt = {"type": "text", "text": {"content": chunk}}
            if annotations:
                rt["annotations"] = annotations
            rich.append(rt)

    return rich if rich else [{"type": "text", "text": {"content": ""}}]


def markdown_to_notion_blocks(md: str) -> list:
    """Convert markdown text to Notion block objects with proper inline formatting."""
    blocks = []
    lines = md.split("\n")

    for line in lines:
        # Headings
        if line.startswith("# "):
            blocks.append({
                "object": "block", "type": "heading_1",
                "heading_1": {"rich_text": parse_inline(line[2:].strip())}
            })
        elif line.startswith("## "):
            blocks.append({
                "object": "block", "type": "heading_2",
                "heading_2": {"rich_text": parse_inline(line[3:].strip())}
            })
        elif line.startswith("### "):
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {"rich_text": parse_inline(line[4:].strip())}
            })
        # Divider
        elif line.strip().startswith("---"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        # Bullet points
        elif line.startswith("- ") or line.startswith("* "):
            content = line[2:].strip()
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": parse_inline(content)}
            })
        # Numbered list
        elif re.match(r'^\d+\. ', line):
            content = re.sub(r'^\d+\. ', '', line).strip()
            blocks.append({
                "object": "block", "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": parse_inline(content)}
            })
        # Table rows — convert to bullet points
        elif line.strip().startswith("|") and line.strip().endswith("|"):
            # Skip separator rows like |---|---|
            if re.match(r'^[\|\s\-:]+$', line.strip()):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            cells = [c for c in cells if c]
            if cells:
                # First row becomes a heading-3, subsequent rows become bullets
                text = " ｜ ".join(cells)
                blocks.append({
                    "object": "block", "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": parse_inline(text)}
                })
        # Empty line → skip
        elif line.strip() == "":
            continue
        # Regular paragraph
        else:
            text = line.strip()
            if text:
                blocks.append({
                    "object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": parse_inline(text)}
                })

    return blocks

# ── Claude API ────────────────────────────────────────────────────────────────
def call_claude(system: str, user: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return message.content[0].text

# ── Notion API ────────────────────────────────────────────────────────────────
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

def create_notion_page(db_id: str, title: str, content: str, report_type: str = "daily") -> str:
    page_payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": DATE_STR}},
            "Type": {"select": {"name": report_type.capitalize()}},
        },
    }

    resp = httpx.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=page_payload)
    resp.raise_for_status()
    page_id = resp.json()["id"]

    # Append content blocks (Notion limits 100 blocks per request)
    blocks = markdown_to_notion_blocks(content)
    for i in range(0, len(blocks), 100):
        chunk = blocks[i:i+100]
        r = httpx.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            json={"children": chunk}
        )
        r.raise_for_status()

    return page_id

def fetch_last_week_reports() -> list[dict]:
    """Query Notion for daily reports from the past 7 days."""
    week_ago  = (TODAY - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    yesterday = (TODAY - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    payload = {
        "filter": {
            "and": [
                {"property": "Date", "date": {"on_or_after": week_ago}},
                {"property": "Date", "date": {"on_or_before": yesterday}},
                {"property": "Type", "select": {"equals": "Daily"}},
            ]
        },
        "sorts": [{"property": "Date", "direction": "ascending"}],
    }
    resp = httpx.post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        headers=NOTION_HEADERS, json=payload
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    reports = []
    for page in results:
        date_val = page["properties"].get("Date", {}).get("date", {})
        date_str = date_val.get("start", "") if date_val else ""

        blocks_resp = httpx.get(
            f"https://api.notion.com/v1/blocks/{page['id']}/children?page_size=200",
            headers=NOTION_HEADERS
        )
        blocks_resp.raise_for_status()
        blocks = blocks_resp.json().get("results", [])

        content_lines = []
        for block in blocks:
            btype = block.get("type", "")
            rich  = block.get(btype, {}).get("rich_text", [])
            text  = "".join(t.get("plain_text", "") for t in rich)
            if text:
                content_lines.append(text)

        if content_lines:
            reports.append({"date": date_str, "content": "\n".join(content_lines)})

    return reports

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{DATE_STR}] Starting brief generation...")

    # 1. Daily report
    print("  → Calling Claude for daily brief...")
    daily_content = call_claude(DAILY_SYSTEM, DAILY_USER)

    daily_title = f"Daily Brief | {DATE_STR}"
    page_id = create_notion_page(NOTION_DB_ID, daily_title, daily_content, report_type="daily")
    print(f"  ✓ Daily brief pushed to Notion (page: {page_id})")

    # 2. Weekly review on Mondays
    if IS_MONDAY:
        print("  → Monday detected — generating weekly review...")
        weekly_reports = fetch_last_week_reports()

        if weekly_reports:
            weekly_prompt  = build_weekly_prompt(weekly_reports)
            weekly_content = call_claude(WEEKLY_SYSTEM, weekly_prompt)

            week_start   = (TODAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            weekly_title = f"Weekly Review | {week_start} ~ {DATE_STR}"
            w_page_id = create_notion_page(NOTION_WEEKLY_DB, weekly_title, weekly_content, report_type="weekly")
            print(f"  ✓ Weekly review pushed to Notion (page: {w_page_id})")
        else:
            print("  ⚠ No daily reports found for last week — skipping weekly review.")

    print("Done.")

if __name__ == "__main__":
    main()
