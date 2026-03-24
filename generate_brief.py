"""
Daily Intelligence Brief Generator — v7.1 (stable)

Base: v7-final
Fixes from v7 → v7.1:
  1. Filter thinking blocks from message history (prevents API format errors)
  2. Explicit Asia/Taipei timezone (correct date on UTC runners)
  3. L3/L4 fallback to "[]" instead of str() (prevents prompt pollution)
  4. Pagination in read_page_content AND safe_overwrite_memo
  5. Dirty state warning in safe_overwrite_memo
  6. Weekend guard in main()
  7. Narrator max_tokens 4500 → 5500 (P1: Knowledge Desk truncation fix)
  8. Analyst prompt: "四種" → "五種" attack types (matches actual 5)

Architecture:
  - Analyst + DA (Sonnet, 3 searches, merged with skepticism taxonomy)
  - Narrator (Sonnet, full 8-section structure)
  - Layer Update (Haiku — invisible plumbing)
  - Weekly Review (Sonnet — quality matters)

Cost profile (~$5/month):
  - Sonnet for Analyst + Narrator + Weekly (user-facing quality)
  - Haiku for Layer Update only (invisible plumbing)
  - 3 searches/day × $0.01
"""

import os
import re
import json
import time
import datetime
import zoneinfo
import anthropic
import httpx

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY    = os.environ["NOTION_API_KEY"]
NOTION_DB_ID      = os.environ["NOTION_DATABASE_ID"]
NOTION_WEEKLY_DB  = os.environ.get("NOTION_WEEKLY_DB_ID", NOTION_DB_ID)

MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU  = "claude-haiku-4-5-20251001"

TW        = zoneinfo.ZoneInfo("Asia/Taipei")
TODAY      = datetime.datetime.now(TW).date()
YESTERDAY  = TODAY - datetime.timedelta(days=1)
WEEKDAY    = TODAY.weekday()
IS_MONDAY  = WEEKDAY == 0
IS_WEEKEND = WEEKDAY >= 5
DATE_STR   = TODAY.strftime("%Y-%m-%d")
DATE_LABEL = TODAY.strftime("%Y年%m月%d日（%A）").replace(
    "Monday","週一").replace("Tuesday","週二").replace("Wednesday","週三").replace(
    "Thursday","週四").replace("Friday","週五").replace("Saturday","週六").replace("Sunday","週日")

PERIPHERY_SCHEDULE = {
    0: ("西非 + 薩赫勒地區",                   "West Africa Sahel security 2026"),
    1: ("東南亞 + 湄公河流域",                 "Southeast Asia Mekong geopolitics 2026"),
    2: ("中東邊陲（葉門、伊拉克、黎巴嫩）",   "Yemen Iraq Lebanon conflict 2026"),
    3: ("拉丁美洲（委內瑞拉、阿根廷、厄瓜多）","Venezuela Argentina Ecuador 2026"),
    4: ("中亞 + 高加索",                        "Central Asia Caucasus geopolitics 2026"),
}
PERIPHERY_LABEL, PERIPHERY_QUERY = PERIPHERY_SCHEDULE.get(WEEKDAY, PERIPHERY_SCHEDULE[0])

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
TIMEOUT     = httpx.Timeout(60.0, connect=10.0)
MAX_RETRIES = 3
RETRY_DELAY = 5

LAYER2_TITLE      = "__WeeklyCompressed__"
LAYER3_TITLE      = "__LongTermTracker__"
LAYER4_TITLE      = "__DevilsAdvocateLog__"
KNOWLEDGE_HISTORY = "__KnowledgeHistory__"

# ── Retry helper ──────────────────────────────────────────────────────────────
def with_retry(fn, *args, retries=MAX_RETRIES, delay=RETRY_DELAY, **kwargs):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_exc = e
            print(f"    ⚠ Network error attempt {attempt}/{retries}: {e}")
            if attempt < retries:
                time.sleep(delay * attempt)
        except httpx.HTTPStatusError as e:
            last_exc = e
            if e.response.status_code == 429:
                print(f"    ⚠ Rate limited attempt {attempt}/{retries}")
                if attempt < retries:
                    time.sleep(delay * attempt * 2)
            elif e.response.status_code >= 500:
                print(f"    ⚠ Server error {e.response.status_code} attempt {attempt}/{retries}")
                if attempt < retries:
                    time.sleep(delay * attempt)
            else:
                raise
        except anthropic.RateLimitError as e:
            last_exc = e
            print(f"    ⚠ Anthropic rate limit attempt {attempt}/{retries}")
            if attempt < retries:
                time.sleep(delay * attempt * 3)
        except anthropic.APIStatusError as e:
            last_exc = e
            if e.status_code >= 500:
                print(f"    ⚠ Anthropic server error {e.status_code} attempt {attempt}/{retries}")
                if attempt < retries:
                    time.sleep(delay * attempt)
            else:
                raise
        except Exception as e:
            last_exc = e
            print(f"    ⚠ Unexpected error attempt {attempt}/{retries}: {e}")
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"All {retries} attempts failed: {last_exc}") from last_exc

# ── Analyst + Devil's Advocate (merged, Sonnet, 3 searches) ──────────────────
ANALYST_SYSTEM = """你是全球宏觀對沖基金的情報分析師兼首席風險官。

任務：生成高密度情報草稿，同時對每個核心判斷自我批評。

分析規則：
- 只對 1-2 個 highest-impact 事件走完整 So What 鏈。其餘事件簡要帶過。
- So What 鏈：事實（數據）→ 經濟機制 → 誰得利/受損 → 風險定價狀態（已定價/部分定價/未定價/過度定價）→ 二階效應 → 資產影響
- 每個核心判斷後執行五種結構化攻擊，標記為【攻擊結果】：
  1. regime_misclassification — 若 regime 判斷錯誤，最可能的替代解讀是哪一種？
  2. timing_error — 方向正確但時機錯誤的條件是什麼？需要什麼才能讓 thesis 成立？
  3. reflexivity_break — 市場倉位是否已定價此 thesis？共識是否已強到讓 thesis 失效？
  4. second_order_inversion — 在什麼條件下因果鏈會反轉？（例：油價上漲通常通膨，但若需求崩潰則反轉為通縮）
  5. omitted_variable_bias — 因果鏈正確，但有哪個隱藏變數被忽略？（例：oil↑→inflation↑，但忽略了庫存周期或中國需求衝擊）
  攻擊後修正 thesis：若攻擊改變了判斷，標注修正後的版本。
- 記錄反向訊號

Knowledge Desk 規則：
- 查看提供的近期主題列表，避免高度重複
- 難度在三個層級間輪換：concept（基礎概念）→ mechanism（運作機制）→ structural（結構性變化）

Thesis 規則：
- 若分析中產生新的長期結構性判斷，在草稿末尾用以下格式標記：
  NEW_THESIS: {"name": "...", "statement": "...", "assets": [...], "invalidators": [...]}
- 若今日證據使某個現有 thesis 失效，標記：
  INVALIDATE_THESIS: {"name": "..."}

風格：繁體中文，保留英文術語。直接輸出，不要開場白。
你會進行 3 次 web_search，嚴格依序，不多不少。"""

def build_analyst_prompt(layer1: str, layer2: str, layer3: str,
                          layer4: str, knowledge_history: str) -> str:
    ctx = ""
    if layer1:
        ctx += f"\n### 昨日摘要\n{layer1}\n"
    if layer2:
        ctx += f"\n### 本週市場結構\n{layer2}\n"
    if layer3:
        ctx += f"\n### 現有 Thesis 清單\n{layer3}\n"
    if layer4:
        ctx += f"\n### 過往推理偏誤記錄\n{layer4}\n"
    if knowledge_history:
        ctx += f"\n### Knowledge Desk 近期主題（避免重複）\n{knowledge_history}\n"
    if ctx:
        ctx = f"\n---\n{ctx}\n---\n"

    return f"""{DATE_LABEL} 情報草稿。

3次搜尋（依序，不多不少）：
1. "markets SPX oil gold bonds {DATE_STR}"
2. "geopolitics macro policy {DATE_STR}"
3. "{PERIPHERY_QUERY}"
{ctx}
草稿結構：

## 資產快照
Brent、10Y UST、DXY、SPX、Gold：數值、走勢、市場隱含預期。

## 核心事件
1-2 個 highest-impact 事件走完整 So What 鏈。
每個判斷後加【挑戰：bias_type】。

## 邊陲：{PERIPHERY_LABEL}
局勢、行為者、與全球宏觀的傳導路徑。

## Knowledge Desk 素材
1個概念（避免與近期主題重複）：
- 概念名稱與難度層級（concept / mechanism / structural）
- 為何今天重要
- 歷史案例（附年份數據）
- 常見誤解
- 何時失效

## 前瞻訊號
48-72hr 內 3-5 個關鍵 catalysts，每個附影響路徑。

## 資產方向
各資產方向、理由、conviction（H/M/L）、主要風險。

（若有新 thesis 或需失效的 thesis，在末尾標記。）"""

# ── Narrator (Sonnet) ─────────────────────────────────────────────────────────
NARRATOR_SYSTEM = """你是宏觀對沖基金的說書人兼導師（The Narrator）。

你同時是三個角色：
- 策略師：分析轉譯成判斷和方向
- 老師：引導讀者思考，不給答案
- 說書人：讓複雜的事有節奏有張力

讀者：政治學背景，志在金融，已有分析肌肉，缺實戰練習量。
目標：15-20分鐘閱讀，每個字都有存在的理由。
核心原則：幫讀者建立自己的分析框架，不是餵結論。

特別要求：
- 若今日資產方向與昨日不同，必須用一句話說明變化原因
- Risk Map 每個風險附主觀機率區間
- conviction 定義（嚴格遵守，跨日可比）：
  H = 65–80% 機率方向正確
  M = 55–65% 機率方向正確
  L = 45–55% 接近硬幣，方向有根據但不確定

格式規則：
- 繁體中文，保留英文術語
- 禁止 Markdown 表格、emoji（🔴🟠🟡除外）
- 直接輸出報告，不要開場白
- ## 標題，### 子標題
- 段落2-3句連貫，bullet 用 -
- 破折號（——）只用於強調
- 重要時間標注台灣時間"""

def build_narrator_prompt(analyst_draft: str) -> str:
    return f"""整合以下草稿（含【挑戰】自我批評），輸出最終報告。
把【挑戰】的內容自然融入敘事，展現分析的複雜性，不要另起段落標注。

=== 草稿 ===
{analyst_draft}

嚴格8段結構：

# Daily Intelligence Brief
{DATE_LABEL} | Strategy & Political Economy Desk

---

## 一、今日張力
一句話核心矛盾——不是摘要，是讓讀者帶著問題讀完報告的引子。

---

## 二、數據切面
5條（Brent、10Y UST、DXY、SPX、Gold）：
- **指標（縮寫）**（中文）數值 ↑/↓ — 一句意義 + 隱含定價判讀

---

## 三、今日主線
最重要的一個事件或結構。說書人風格，起承轉合。
包含完整 So What 鏈，自然融入【挑戰】的複雜性。
若方向與昨日不同，說明變化原因。300字內。

---

## 四、權力地圖

### 得利方
行為者：原因（每條一行）

### 受損方
行為者：原因（每條一行）

### Risk Map
- 🔴 高風險（30-40%）：事件 + 影響路徑
- 🟠 中風險（15-25%）：事件 + 影響路徑
- 🟡 監控（<15%）：事件 + 原因

### 今日關鍵變數
一句話——決定走向的那件事。

---

## 五、邊陲訊號：{PERIPHERY_LABEL}
2段。第一段：局勢與地理邏輯。
第二段：與今日主線的具體傳導路徑（資金流、供應鏈、政治聯盟）。

---

## 六、配置羅盤

### 方向判斷
5條（美股、美債、外匯、原油、黃金）：
- **資產（縮寫）↑/↓** — 邏輯 + conviction（H/M/L）

### 前瞻監控（48-72hr）
3-5個 catalysts：
- 事件（台灣時間）— 重要性 + 影響路徑

---

## 七、Knowledge Desk

### 概念：[名稱]
**為什麼今天重要**：一句話連結今日報告。
**實戰應用**：交易配置中如何影響決策？什麼條件下失效？典型錯誤理解？2-3段連貫段落。
**歷史案例**：一個真實案例，附年份與結果。
**當前關鍵問題**：基於今日環境，最值得追蹤的一個開放性問題。

---

## 八、今日思考題
一個開放性問題，無標準答案，讓讀者帶著觀察接下來幾天。
若昨日有思考題，先一句話回應其進展。

---
**資料來源**
1-3條：機構 — 標題，日期"""

# ── Layer Update (Haiku) ──────────────────────────────────────────────────────
LAYER_UPDATE_SYSTEM = """宏觀對沖基金資料管理員。輸出合法 JSON，不加說明或代碼塊。"""

def build_layer_update_prompt(report_summary: str, analyst_draft: str,
                               old_l2: str, old_l3: str, old_l4: str,
                               old_kh: str) -> str:
    thesis_signals = ""
    for line in analyst_draft.split("\n"):
        if "NEW_THESIS:" in line or "INVALIDATE_THESIS:" in line:
            thesis_signals += line.strip() + "\n"

    return f"""更新記憶層。輸出純 JSON（無 markdown）：

{{"layer2": "更新後 L2 文字", "layer3": [...], "layer4": [...], "knowledge_topic": "主題名稱"}}

今日摘要（{DATE_STR}）：
{report_summary}

Thesis 訊號：
{thesis_signals or "（今日無新 thesis）"}

現有 L2（7天每日壓縮）：
{old_l2 or "（空）"}

現有 L3（thesis JSON 清單）：
{old_l3 or "[]"}

現有 L4（偏誤記錄）：
{old_l4 or "[]"}

規則：
L2：末尾加今日條目，格式如下（嚴格遵守，每行一個欄位）：
{DATE_STR}
regime: [當前市場 regime，例：late-cycle geopolitical risk premium]
driver: [今日最主要的價格驅動力]
policy: [Fed/主要央行偏向，例：on hold / hawkish / pivot signal]
fragility: [最脆弱的資產或市場節點]
刪除 >7天的條目。
L3：JSON 陣列，每個 thesis 格式：{{"name":"...","statement":"...","date":"...","assets":[...],"invalidators":[...],"status":"active"}}
- 加入 NEW_THESIS 標記的項目
- 將 INVALIDATE_THESIS 標記的項目 status 改為 "invalidated"
- 刪除 >30天且 status=invalidated 的項目
L4：JSON 陣列，每條 {{"date":"...","attack_type":"...","description":"...","thesis_revised":true/false}}
- attack_type 必須是：regime_misclassification / timing_error / reflexivity_break / second_order_inversion / omitted_variable_bias
- 加入今日最重要的 1 條攻擊記錄，標注是否導致 thesis 修正
- 刪除 >14天的項目"""

# ── Weekly Review (Sonnet) ────────────────────────────────────────────────────
WEEKLY_SYSTEM = """你是宏觀對沖基金資深策略師，負責週度總結。
繁體中文，保留英文術語。禁止表格，段落為主，必要時用 bullet points。"""

def build_weekly_prompt(layer2: str, layer3: str) -> str:
    week_start = (TODAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    return f"""本週每日判斷：
{layer2 or "（無）"}

Thesis 清單：
{layer3 or "[]"}

# Weekly Intelligence Review
{week_start} ~ {DATE_STR} | Strategy & Political Economy Desk

## 本週核心主題
3-5個貫穿全週的主線敘事，說明演進軌跡，用段落寫。

## 跨資產表現回顧
各資產類別本週關鍵走勢與驅動因素。

## 預測 vs 實際
回顧本週核心判斷：哪些兌現、哪些偏離、原因是什麼。

## Thesis 追蹤
哪些 thesis 本週得到強化、哪些動搖、哪些失效。

## 思考題追蹤
本週思考題的集體回顧：哪些得到答案，哪些仍在演變。

## 下週關鍵觀察點
- 最重要的5個 catalysts 或數據點

## 週度 Meta Insight
本週最重要的一個洞見，一段話，不超過150字。

---
**資料來源**（5條）"""

# ── Claude API ────────────────────────────────────────────────────────────────
def call_claude_with_search(system: str, user: str) -> str:
    """Analyst with web search on Sonnet + extended thinking. Cap at 6 iterations."""
    client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": user}]

    for _ in range(6):
        response = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=5000,
            thinking={
                "type": "enabled",
                "budget_tokens": 2000,
            },
            system=system,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )

        # Collect text from non-thinking blocks only
        text_blocks = [b.text for b in response.content
                       if hasattr(b, "text") and b.type != "thinking"]

        if response.stop_reason == "end_turn":
            return "\n".join(text_blocks)

        # Strip thinking blocks before appending to message history
        # (API rejects thinking blocks in subsequent turns)
        filtered_content = [b for b in response.content if b.type != "thinking"]
        messages.append({"role": "assistant", "content": filtered_content})

        tool_results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": "Search executed."}
            for b in response.content if b.type == "tool_use"
        ]
        if not tool_results:
            return "\n".join(text_blocks)
        messages.append({"role": "user", "content": tool_results})

    # Final extraction after loop exhaustion
    return "\n".join([b.text for b in response.content
                      if hasattr(b, "text") and b.type != "thinking"])


def call_claude(system: str, user: str, model: str, max_tokens: int = 3000) -> str:
    """Standard call without tools."""
    client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=model,
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
    resp = with_retry(httpx.post, url, headers=NOTION_HEADERS, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def notion_patch(url: str, payload: dict) -> dict:
    resp = with_retry(httpx.patch, url, headers=NOTION_HEADERS, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def notion_get(url: str) -> dict:
    resp = with_retry(httpx.get, url, headers=NOTION_HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def notion_delete(url: str):
    with_retry(httpx.delete, url, headers=NOTION_HEADERS, timeout=TIMEOUT)


def read_page_content(page_id: str, page_size: int = 200) -> str:
    """Read all text from a Notion page. Handles pagination."""
    all_lines = []
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size={page_size}"

    while url:
        data = notion_get(url)
        for block in data.get("results", []):
            btype = block.get("type", "")
            rich  = block.get(btype, {}).get("rich_text", [])
            text  = "".join(t.get("plain_text", "") for t in rich)
            if text:
                all_lines.append(text)

        if data.get("has_more") and data.get("next_cursor"):
            base = f"https://api.notion.com/v1/blocks/{page_id}/children"
            url  = f"{base}?page_size={page_size}&start_cursor={data['next_cursor']}"
        else:
            url = None

    return "\n".join(all_lines)


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
    data    = notion_post(
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
    return read_page_content(find_or_create_memo(title))


def safe_overwrite_memo(title: str, new_content: str):
    """Write new blocks first, then delete old ones (safe against mid-op failure)."""
    page_id = find_or_create_memo(title)

    # Collect ALL old block IDs (paginated)
    old_ids = []
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
    while url:
        data = notion_get(url)
        old_ids.extend(b["id"] for b in data.get("results", []))
        if data.get("has_more") and data.get("next_cursor"):
            base = f"https://api.notion.com/v1/blocks/{page_id}/children"
            url  = f"{base}?page_size=100&start_cursor={data['next_cursor']}"
        else:
            url = None

    append_blocks(page_id, new_content)
    failed_deletes = []
    for block_id in old_ids:
        try:
            notion_delete(f"https://api.notion.com/v1/blocks/{block_id}")
        except Exception as e:
            failed_deletes.append(block_id)
            print(f"    ⚠ Could not delete old block {block_id}: {e}")
    if failed_deletes:
        print(f"    ⛔ DIRTY STATE: {title} has {len(failed_deletes)} stale blocks "
              f"({', '.join(failed_deletes[:3])}...)")

# ── Memory helpers ────────────────────────────────────────────────────────────
def fetch_layer1() -> str:
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
    return content[:1000] + "…" if len(content) > 1000 else content


def parse_layer_update(raw: str, old_l2: str, old_kh: str,
                        report_summary: str) -> tuple[str, str, str, str]:
    """Parse layer update JSON. Returns (l2, l3, l4, knowledge_topic).
    Fallback keeps Layer 2 alive if JSON fails."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?\s*```$", "", raw)
    raw = raw.strip()

    try:
        data = json.loads(raw)
        l2 = data.get("layer2", "")
        l3_raw = data.get("layer3", [])
        l4_raw = data.get("layer4", [])
        # Validate: must be list, otherwise reset to empty array
        l3 = json.dumps(l3_raw, ensure_ascii=False, indent=2) if isinstance(l3_raw, list) else "[]"
        l4 = json.dumps(l4_raw, ensure_ascii=False, indent=2) if isinstance(l4_raw, list) else "[]"
        kt = data.get("knowledge_topic", "")
        if l2:
            return l2, l3, l4, kt
    except json.JSONDecodeError as e:
        print(f"    ⚠ JSON parse failed: {e}")

    # Fallback: keep Layer 2 alive
    print("    → Fallback: appending today to L2")
    today_entry = f"{DATE_STR}：{report_summary[:100]}"
    if old_l2:
        cutoff = (TODAY - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        lines  = old_l2.strip().split("\n")
        kept   = [ln for ln in lines
                  if not re.match(r"^\d{4}-\d{2}-\d{2}", ln) or ln[:10] >= cutoff]
        kept.append(today_entry)
        return "\n".join(kept), "[]", "[]", ""
    return today_entry, "[]", "[]", ""


def update_knowledge_history(old_kh: str, new_topic: str) -> str:
    """Append today's topic, keep last 10 entries."""
    if not new_topic:
        return old_kh
    entries = [ln.strip() for ln in old_kh.strip().split("\n") if ln.strip()] if old_kh else []
    entries.append(f"{DATE_STR}: {new_topic}")
    return "\n".join(entries[-10:])

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if IS_WEEKEND:
        print(f"[{DATE_STR}] Weekend — skipping daily brief.")
        return

    print(f"[{DATE_STR}] Daily Intelligence Brief v7.1 — {PERIPHERY_LABEL}")
    print(f"  Analyst/Narrator/Weekly: {MODEL_SONNET} | Layer: {MODEL_HAIKU}")

    # ── 1. Load memory ────────────────────────────────────────────────────────
    print("  → Loading memory...")
    try:
        layer1            = fetch_layer1()
        layer2            = read_memo(LAYER2_TITLE)
        layer3            = read_memo(LAYER3_TITLE)
        layer4            = read_memo(LAYER4_TITLE)
        knowledge_history = read_memo(KNOWLEDGE_HISTORY)
        print(f"    L1={'✓' if layer1 else '∅'}  L2={'✓' if layer2 else '∅'}  "
              f"L3={'✓' if layer3 else '∅'}  L4={'✓' if layer4 else '∅'}  "
              f"KH={'✓' if knowledge_history else '∅'}")
    except Exception as e:
        print(f"    ⚠ Memory load failed ({e})")
        layer1 = layer2 = layer3 = layer4 = knowledge_history = ""

    # ── 2. Analyst + DA (Sonnet, 3 searches) ──────────────────────────────────
    print("  → [Analyst+DA] Draft (Sonnet, 3 searches)...")
    analyst_draft = with_retry(
        call_claude_with_search,
        ANALYST_SYSTEM,
        build_analyst_prompt(layer1, layer2, layer3, layer4, knowledge_history),
    )
    print(f"  ✓ Draft ({len(analyst_draft)} chars)")

    # ── 3. Narrator (Sonnet) ──────────────────────────────────────────────────
    print("  → [Narrator] Final report (Sonnet)...")
    final_report = with_retry(
        call_claude,
        NARRATOR_SYSTEM,
        build_narrator_prompt(analyst_draft),
        MODEL_SONNET,
        max_tokens=5500,
    )
    print(f"  ✓ Report ({len(final_report)} chars)")

    # ── 4. Push to Notion FIRST ───────────────────────────────────────────────
    print("  → Pushing to Notion...")
    page_id = create_page(NOTION_DB_ID, f"📊 Daily Brief | {DATE_STR}", "daily")
    append_blocks(page_id, final_report)
    print(f"  ✓ Pushed (page: {page_id})")

    # ── 5. Update memory (Haiku) ──────────────────────────────────────────────
    print("  → Updating memory (Haiku)...")
    try:
        report_summary = final_report[:1000]
        update_raw = call_claude(
            LAYER_UPDATE_SYSTEM,
            build_layer_update_prompt(
                report_summary, analyst_draft,
                layer2, layer3, layer4, knowledge_history
            ),
            MODEL_HAIKU,
            max_tokens=1200,
        )
        new_l2, new_l3, new_l4, new_kt = parse_layer_update(
            update_raw, layer2, knowledge_history, report_summary
        )
        if new_l2:
            safe_overwrite_memo(LAYER2_TITLE, new_l2)
        if new_l3 and new_l3 != "[]":
            safe_overwrite_memo(LAYER3_TITLE, new_l3)
        if new_l4 and new_l4 != "[]":
            safe_overwrite_memo(LAYER4_TITLE, new_l4)
        updated_kh = update_knowledge_history(knowledge_history, new_kt)
        if updated_kh:
            safe_overwrite_memo(KNOWLEDGE_HISTORY, updated_kh)
        print(f"  ✓ Memory (L2={'✓' if new_l2 else '∅'} "
              f"L3={'✓' if new_l3 and new_l3 != '[]' else '∅'} "
              f"L4={'✓' if new_l4 and new_l4 != '[]' else '∅'} "
              f"KH={'✓' if new_kt else '∅'})")
    except Exception as e:
        print(f"  ⚠ Memory update failed ({e}) — report saved")

    # ── 6. Weekly on Monday (Sonnet) ──────────────────────────────────────────
    if IS_MONDAY:
        print("  → Weekly review (Sonnet)...")
        try:
            fresh_l2 = read_memo(LAYER2_TITLE)
            fresh_l3 = read_memo(LAYER3_TITLE)
            weekly = with_retry(
                call_claude,
                WEEKLY_SYSTEM,
                build_weekly_prompt(fresh_l2, fresh_l3),
                MODEL_SONNET,
                max_tokens=3000,
            )
            week_start = (TODAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            w_id = create_page(
                NOTION_WEEKLY_DB,
                f"📅 Weekly Review | {week_start} ~ {DATE_STR}",
                "weekly"
            )
            append_blocks(w_id, weekly)
            print(f"  ✓ Weekly pushed (page: {w_id})")
        except Exception as e:
            print(f"  ⚠ Weekly failed ({e})")

    print("Done.")


if __name__ == "__main__":
    main()
