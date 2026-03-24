import os
import re
import json
import time
import datetime
import anthropic
import httpx
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY    = os.environ["NOTION_API_KEY"]
NOTION_DB_ID      = os.environ["NOTION_DATABASE_ID"]
NOTION_WEEKLY_DB  = os.environ.get("NOTION_WEEKLY_DB_ID", NOTION_DB_ID)
FRED_API_KEY      = os.environ.get("FRED_API_KEY", "")

# GitHub Actions Environment Variables
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "") # Format: owner/repo
GITHUB_REF_NAME   = os.environ.get("GITHUB_REF_NAME", "main")

# v8.5 旗艦視覺化配置：Opus (分析) + Sonnet (敘事) + Haiku (校驗) + GitHub (託管)
MODEL_OPUS   = "claude-3-opus-20240229"
MODEL_SONNET = "claude-3-5-sonnet-20241022"
MODEL_HAIKU  = "claude-3-5-haiku-20241022"

TODAY     = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)
WEEKDAY   = TODAY.weekday()
IS_MONDAY = WEEKDAY == 0
DATE_STR  = TODAY.strftime("%Y-%m-%d")
DATE_LABEL = TODAY.strftime("%Y年%m月%d日（%A）").replace(
    "Monday","週一").replace("Tuesday","週二").replace("Wednesday","週三").replace(
    "Thursday","週四").replace("Friday","週五").replace("Saturday","週六").replace("Sunday","週日")

PERIPHERY_SCHEDULE = {
    0: ("西非 + 薩赫勒地區",                    "West Africa Sahel security 2026"),
    1: ("東南亞 + 湄公河流域",                  "Southeast Asia Mekong geopolitics 2026"),
    2: ("中東邊陲（葉門、伊拉克、黎巴嫩）",    "Yemen Iraq Lebanon conflict 2026"),
    3: ("拉丁美洲（委內瑞拉、阿根廷、厄瓜多）", "Venezuela Argentina Ecuador 2026"),
    4: ("中亞 + 高加索",                         "Central Asia Caucasus geopolitics 2026"),
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

# ── Retry ─────────────────────────────────────────────────────────────────────
def with_retry(fn, *args, retries=MAX_RETRIES, delay=RETRY_DELAY, **kwargs):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_exc = e
            print(f"    ⚠ Network error attempt {attempt}/{retries}: {e}")
            if attempt < retries: time.sleep(delay * attempt)
        except httpx.HTTPStatusError as e:
            last_exc = e
            if e.response.status_code == 429:
                print(f"    ⚠ Rate limited attempt {attempt}/{retries}")
                if attempt < retries: time.sleep(delay * attempt * 2)
            elif e.response.status_code >= 500:
                if attempt < retries: time.sleep(delay * attempt)
                else: raise
            else: raise
        except anthropic.RateLimitError as e:
            last_exc = e
            print(f"    ⚠ Anthropic rate limit attempt {attempt}/{retries}")
            if attempt < retries: time.sleep(delay * attempt * 3)
        except anthropic.APIStatusError as e:
            last_exc = e
            if e.status_code >= 500:
                if attempt < retries: time.sleep(delay * attempt)
                else: raise
            else: raise
        except Exception as e:
            last_exc = e
            print(f"    ⚠ Unexpected error attempt {attempt}/{retries}: {e}")
            if attempt < retries: time.sleep(delay)
    raise RuntimeError(f"All {retries} attempts failed") from last_exc

# ── Visualization Layer ───────────────────────────────────────────────────────
def generate_correlation_heatmap(corr_matrix: pd.DataFrame) -> tuple[str, str]:
    """Generates a heatmap image and returns the local path and GitHub raw URL."""
    try:
        plt.figure(figsize=(10, 8))
        sns.set_theme(style="white")
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
        f, ax = plt.subplots(figsize=(11, 9))
        cmap = sns.diverging_palette(230, 20, as_cmap=True)
        sns.heatmap(corr_matrix, mask=mask, cmap=cmap, vmax=1.0, vmin=-1.0, center=0,
                    square=True, linewidths=.5, cbar_kws={"shrink": .5}, annot=True, fmt=".2f")
        plt.title(f"Asset Correlation Matrix ({DATE_STR})", fontsize=16)
        
        # Ensure 'assets' directory exists for GitHub hosting
        if not os.path.exists("assets"):
            os.makedirs("assets")
            
        filename = f"assets/correlation_{DATE_STR}.png"
        plt.savefig(filename, bbox_inches='tight', dpi=150)
        plt.close()
        
        # Build GitHub Raw URL for Notion
        if GITHUB_REPOSITORY:
            raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_REF_NAME}/{filename}"
            return filename, raw_url
        return filename, ""
    except Exception as e:
        print(f"    ⚠ Heatmap generation failed: {e}")
        return "", ""

# ── Data Layer ────────────────────────────────────────────────────────────────
def fetch_yfinance_data() -> tuple[dict, pd.DataFrame]:
    try: import yfinance as yf
    except ImportError: return {}, pd.DataFrame()
    tickers = {"SPX": "^GSPC", "Brent": "BZ=F", "Gold": "GC=F", "DXY": "DX-Y.NYB", "UST10Y": "^TNX", "VIX": "^VIX"}
    results = {}
    try:
        data = yf.download(list(tickers.values()), period="10d", interval="1d", progress=False, threads=True)
        if data.empty: return {}, pd.DataFrame()
        close = data["Close"]
        subset = close[list(tickers.values())].tail(5)
        inv_tickers = {v: k for k, v in tickers.items()}
        subset.columns = [inv_tickers.get(c, c) for c in subset.columns]
        corr_df = subset.corr()
        for name, tk in tickers.items():
            s = close[tk].dropna()
            if len(s) >= 2:
                lat, prev = float(s.iloc[-1]), float(s.iloc[-2])
                results[name] = {"price": round(lat, 2), "change": round(lat - prev, 2), "pct": round((lat - prev) / prev * 100, 2), "date": str(s.index[-1].date())}
        return results, corr_df
    except: return {}, pd.DataFrame()

def fetch_fred_data() -> dict:
    if not FRED_API_KEY: return {}
    try: from fredapi import Fred
    except: return {}
    series = {"Fed Funds Rate": "DFF", "2Y Treasury": "DGS2", "10Y Treasury": "DGS10", "Yield Curve (10Y-2Y)": "T10Y2Y", "Breakeven Inflation": "T10YIE"}
    results = {}
    try:
        fred = Fred(api_key=FRED_API_KEY)
        start = YESTERDAY - datetime.timedelta(days=10)
        for name, sid in series.items():
            s = fred.get_series(sid, observation_start=start).dropna()
            if len(s) >= 2:
                lat, prev = float(s.iloc[-1]), float(s.iloc[-2])
                results[name] = {"value": round(lat, 3), "prev": round(prev, 3), "change": round(lat - prev, 3), "date": str(s.index[-1].date())}
        return results
    except: return {}

def format_market_data(yfd: dict, frd: dict, corr_df: pd.DataFrame) -> tuple[str, dict]:
    hard_truths = {}
    lines = ["## 預載市場數據\n"]
    if not corr_df.empty: lines.append("（相關性熱圖已生成並上傳至 GitHub 倉庫 assets 目錄。）\n")
    if yfd:
        lines.append("### 價格（yfinance）")
        for n, d in yfd.items():
            dr = "↑" if d["change"] > 0 else "↓" if d["change"] < 0 else "→"
            lines.append(f"- {n}: {d['price']} ({dr} {d['pct']:+.2f}%) [{d['date']}]")
    if frd:
        lines.append("\n### 宏觀指標（FRED）")
        for n, d in frd.items():
            dr = "↑" if d["change"] > 0 else "↓" if d["change"] < 0 else "→"
            lines.append(f"- {n}: {d['value']} ({dr} {d['change']:+.3f}) [{d['date']}]")
        be, nom_10y = frd.get("Breakeven Inflation", {}), frd.get("10Y Treasury", {})
        if be.get("value") and nom_10y.get("value"):
            ry_today = nom_10y["value"] - be["value"]
            hard_truths["real_yield_value"] = round(ry_today, 3)
            lines.append(f"\n- 實質利率 (10Y Real Yield): {ry_today:.3f}%")
    return "\n".join(lines), hard_truths

# ── Analyst + Narrator (Standard Logic) ───────────────────────────────────────
ANALYST_SYSTEM = "你是全球頂尖宏觀對沖基金的資深分析師（Opus 旗艦配置）。繁體中文，保留英文術語。"
NARRATOR_SYSTEM = "你是宏觀對沖基金的首席說書人。Show, Don't Tell。繁體中文輸出。"

def call_claude_with_search(system: str, user: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": user}]
    for _ in range(3):
        response = client.messages.create(model=MODEL_OPUS, max_tokens=4000, system=system, tools=[{"type": "web_search_20250305", "name": "web_search"}], messages=messages)
        if response.stop_reason == "end_turn": return "\n".join([b.text for b in response.content if hasattr(b, "text")])
        messages.append({"role": "assistant", "content": response.content})
        tool_results = [{"type": "tool_result", "tool_use_id": b.id, "content": "Search executed."} for b in response.content if b.type == "tool_use"]
        messages.append({"role": "user", "content": tool_results})
    return ""

def call_claude(system: str, user: str, model: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return client.messages.create(model=model, max_tokens=4000, system=system, messages=[{"role": "user", "content": user}]).content[0].text

# ── Notion (Standard Blocks) ──────────────────────────────────────────────────
def markdown_to_notion_blocks(md: str, image_url: str = None) -> list:
    blocks = []
    for line in md.split("\n"):
        line = line.strip()
        if not line: continue
        if line.startswith("# "): blocks.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
        elif line.startswith("## "): 
            blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:]}}]}})
            if "數據切面" in line and image_url:
                blocks.append({"object": "block", "type": "image", "image": {"type": "external", "external": {"url": image_url}}})
        elif line.startswith("### "): blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:]}}]}})
        elif line.startswith("- "): blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
        else: blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}})
    return blocks

def create_page(db_id: str, title: str, content: str, image_url: str = None):
    blocks = markdown_to_notion_blocks(content, image_url)
    payload = {
        "parent": {"database_id": db_id},
        "properties": {"Name": {"title": [{"text": {"content": title}}]}, "Date": {"date": {"start": DATE_STR}}, "Type": {"select": {"name": "Daily"}}},
        "children": blocks[:100]
    }
    resp = with_retry(httpx.post, "https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{DATE_STR}] v8.5 GitHub Edition Running...")
    yfd, corr_df = fetch_yfinance_data()
    frd = fetch_fred_data()
    
    heatmap_path, heatmap_url = "", ""
    if not corr_df.empty:
        heatmap_path, heatmap_url = generate_correlation_heatmap(corr_df)
        print(f"  ✓ Heatmap generated: {heatmap_path} | URL: {heatmap_url}")

    market_data, _ = format_market_data(yfd, frd, corr_df)
    analyst_draft = with_retry(call_claude_with_search, ANALYST_SYSTEM, f"今日數據：\n{market_data}\n請生成深度分析。")
    final_report = with_retry(call_claude, NARRATOR_SYSTEM, f"分析草稿：\n{analyst_draft}\n請生成最終報告。")
    
    create_page(NOTION_DB_ID, f"🏛️ Daily Brief | {DATE_STR}", final_report, heatmap_url)
    print("  ✓ Notion Pushed.")

if __name__ == "__main__":
    main()
