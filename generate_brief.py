import os
import re
import json
import time
import datetime
import anthropic
import httpx
import pandas as pd
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY    = os.environ["NOTION_API_KEY"]
NOTION_DB_ID      = os.environ["NOTION_DATABASE_ID"]
NOTION_WEEKLY_DB  = os.environ.get("NOTION_WEEKLY_DB_ID", NOTION_DB_ID)
FRED_API_KEY      = os.environ.get("FRED_API_KEY", "")

# 官方正確 API 模型名稱
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
            if attempt < retries:
                time.sleep(delay * attempt)
        except httpx.HTTPStatusError as e:
            last_exc = e
            if e.response.status_code == 429:
                print(f"    ⚠ Rate limited attempt {attempt}/{retries}")
                if attempt < retries:
                    time.sleep(delay * attempt * 2)
            elif e.response.status_code >= 500:
                if attempt < retries:
                    time.sleep(delay * attempt)
                else:
                    raise
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
                if attempt < retries:
                    time.sleep(delay * attempt)
                else:
                    raise
            else:
                raise
        except Exception as e:
            last_exc = e
            print(f"    ⚠ Unexpected error attempt {attempt}/{retries}: {e}")
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"All {retries} attempts failed") from last_exc

# ── Data Layer ────────────────────────────────────────────────────────────────
def fetch_yfinance_data() -> tuple[dict, str]:
    try:
        import yfinance as yf
    except ImportError:
        print("    ⚠ yfinance not installed"); return {}, ""
    tickers = {
        "SPX":   "^GSPC",
        "Brent": "BZ=F",
        "Gold":  "GC=F",
        "DXY":   "DX-Y.NYB",
        "UST10Y":"^TNX",
        "VIX":   "^VIX",
    }
    results = {}
    corr_text = ""
    try:
        data = yf.download(list(tickers.values()), period="10d", interval="1d",
                           progress=False, threads=True)
        if data.empty:
            return {}, ""
        
        close = data["Close"]
        
        # Calculate Correlation Matrix for the last 5 days
        try:
            subset = close[list(tickers.values())].tail(5)
            # Rename columns back to friendly names
            inv_tickers = {v: k for k, v in tickers.items()}
            subset.columns = [inv_tickers.get(c, c) for c in subset.columns]
            corr = subset.corr()
            corr_text = "### 資產相關性矩陣 (Last 5 Days)\n"
            corr_text += "指標說明：1.0 為完全正相關，-1.0 為完全負相關。\n"
            # Format as a simple text table
            header = " | " + " | ".join(corr.columns)
            corr_text += header + "\n"
            corr_text += "-" * len(header) + "\n"
            for idx, row in corr.iterrows():
                row_str = f"{idx} | " + " | ".join([f"{val:.2f}" for val in row])
                corr_text += row_str + "\n"
        except Exception as e:
            print(f"    ⚠ Correlation calculation failed: {e}")

        for name, tk in tickers.items():
            try:
                s = close[tk].dropna()
                if len(s) >= 2:
                    lat, prev = float(s.iloc[-1]), float(s.iloc[-2])
                    results[name] = {
                        "price": round(lat, 2),
                        "change": round(lat - prev, 2),
                        "pct": round((lat - prev) / prev * 100, 2),
                        "date": str(s.index[-1].date()),
                    }
                elif len(s) == 1:
                    results[name] = {
                        "price": round(float(s.iloc[-1]), 2),
                        "change": None, "pct": None,
                        "date": str(s.index[-1].date()),
                    }
            except Exception as e:
                print(f"    ⚠ yf {name}: {e}")
    except Exception as e:
        print(f"    ⚠ yf download: {e}")
    return results, corr_text


def fetch_fred_data() -> dict:
    if not FRED_API_KEY:
        print("    ⚠ No FRED_API_KEY — skipping"); return {}
    try:
        from fredapi import Fred
    except ImportError:
        print("    ⚠ fredapi not installed"); return {}
    series = {
        "Fed Funds Rate":       "DFF",
        "2Y Treasury":          "DGS2",
        "10Y Treasury":         "DGS10",
        "Yield Curve (10Y-2Y)": "T10Y2Y",
        "Breakeven Inflation":  "T10YIE",
        "HY Credit Spread":     "BAMLH0A0HYM2",
    }
    results = {}
    try:
        fred = Fred(api_key=FRED_API_KEY)
        start = YESTERDAY - datetime.timedelta(days=10)
        for name, sid in series.items():
            try:
                s = fred.get_series(sid, observation_start=start).dropna()
                if len(s) >= 2:
                    lat, prev = float(s.iloc[-1]), float(s.iloc[-2])
                    results[name] = {
                        "value": round(lat, 3),
                        "prev": round(prev, 3),
                        "change": round(lat - prev, 3),
                        "date": str(s.index[-1].date()),
                    }
                elif len(s) == 1:
                    results[name] = {
                        "value": round(float(s.iloc[-1]), 3),
                        "prev": None, "change": None,
                        "date": str(s.index[-1].date()),
                    }
            except Exception as e:
                print(f"    ⚠ FRED {name}: {e}")
    except Exception as e:
        print(f"    ⚠ FRED connection: {e}")
    return results


def format_market_data(yfd: dict, frd: dict, corr_text: str) -> tuple[str, dict]:
    if not yfd and not frd:
        return "", {}
    
    hard_truths = {}
    lines = ["## 預載市場數據（API 直取，精確度高於搜尋）\n"]
    
    if corr_text:
        lines.append(corr_text + "\n")

    if yfd:
        lines.append("### 價格（yfinance）")
        for n, d in yfd.items():
            if d["change"] is not None:
                dr = "↑" if d["change"] > 0 else "↓" if d["change"] < 0 else "→"
                lines.append(f"- {n}: {d['price']} ({dr} {d['pct']:+.2f}%) [{d['date']}]")
            else:
                lines.append(f"- {n}: {d['price']} [{d['date']}]")
        lines.append("")
        
    if frd:
        lines.append("### 宏觀指標（FRED）")
        for n, d in frd.items():
            if d["change"] is not None:
                dr = "↑" if d["change"] > 0 else "↓" if d["change"] < 0 else "→"
                lines.append(f"- {n}: {d['value']} ({dr} {d['change']:+.3f}) [{d['date']}]")
            else:
                lines.append(f"- {n}: {d['value']} [{d['date']}]")
        lines.append("")
        
        lines.append("### 衍生訊號（硬核物理引擎計算）")
        yc = frd.get("Yield Curve (10Y-2Y)", {})
        be = frd.get("Breakeven Inflation", {})
        hy = frd.get("HY Credit Spread", {})
        nom_10y = frd.get("10Y Treasury", {})
        
        if yc.get("value") is not None:
            v = yc["value"]
            tag = "倒掛（衰退訊號）" if v < 0 else "平坦（成長前景謹慎）" if v < 0.5 else "正常"
            lines.append(f"- 殖利率曲線：{v}% — {tag}")
            hard_truths["yield_curve_inverted"] = v < 0
            
        if nom_10y.get("value") is not None and be.get("value") is not None:
            # Real Yield = Nominal - Breakeven
            ry_today = nom_10y["value"] - be["value"]
            ry_prev = nom_10y["prev"] - be["prev"] if nom_10y["prev"] is not None and be["prev"] is not None else None
            
            dr = "→"
            if ry_prev is not None:
                ry_change = ry_today - ry_prev
                dr = "↑" if ry_change > 0.001 else "↓" if ry_change < -0.001 else "→"
                hard_truths["real_yield_direction"] = "up" if ry_change > 0.001 else "down" if ry_change < -0.001 else "flat"
            
            lines.append(f"- 實質利率 (10Y Real Yield): {ry_today:.3f}% ({dr}) [計算公式: Nominal - BEI]")
            hard_truths["real_yield_value"] = round(ry_today, 3)

        if hy.get("value") is not None:
            v = hy["value"]
            tag = "壓力區間" if v > 5.0 else "偏緊" if v < 3.5 else "正常"
            lines.append(f"- 高收益信用利差：{v}% — {tag}")
        lines.append("")
        
    lines.append("（直接使用以上數據，不需再搜尋驗證。若敘事與上述計算衝突，以數據為準。）\n")
    return "\n".join(lines), hard_truths

# ── Analyst + Devil's Advocate ────────────────────────────────────────────────
ANALYST_SYSTEM = """你是全球宏觀對沖基金的情報分析師兼首席風險官。

重要：若收到預載市場數據（yfinance + FRED），直接使用，不需搜尋市場價格。3次 web_search 全部用於敘事性搜尋。

【絕對宏觀法則（Macro Physics Engine）】： 在推導跨資產邏輯時，必須嚴格遵守以下數學與金融常理，絕不可為了敘事流暢而扭曲：
實質殖利率 (Real Yield) = 名目殖利率 - 通膨預期 (Breakeven)。 若油價/原物料大跌導致通膨預期重挫，而名目殖利率跌幅較小，則實質殖利率為「上升（Spike）」。
實質殖利率上升 → 壓縮高估值資產（如 SPX 科技股）的估值倍數。
若市場出現上述法則的背離（例如實質利率升、美股卻大漲），必須將其定調為「純粹的倉位回補」或「流動性幻覺」，切勿將其合理化為基本面改善。

分析規則：
- 1-2 個 highest-impact 事件走完整 So What 鏈：事實（數據）→ 經濟機制 → 誰得利/受損 → 風險定價狀態（已定價/部分定價/未定價/過度定價）→ 二階效應 → 資產影響
- 每個核心判斷後執行五種結構化攻擊，標記為【攻擊結果】：
  1. regime_misclassification — 若 regime 判斷錯誤，最可能的替代解讀是哪一種？
  2. timing_error — 方向正確但時機錯誤的條件是什麼？
  3. reflexivity_break — 市場倉位是否已定價此 thesis？共識是否讓 thesis 失效？
  4. second_order_inversion — 在什麼條件下因果鏈會反轉？
  5. omitted_variable_bias — 因果鏈正確，但有哪個隱藏變數被忽略？
  攻擊後：若攻擊改變了判斷，標注修正後的版本。
- 記錄反向訊號

Knowledge Desk 規則：
- 查看近期主題列表，避免高度重複
- 難度輪換：concept → mechanism → structural

Thesis 規則：
- 新判斷：NEW_THESIS: {"name": "...", "statement": "...", "assets": [...], "invalidators": [...]}
- 失效：INVALIDATE_THESIS: {"name": "..."}

繁體中文，保留英文術語。直接輸出，不要開場白。
3次 web_search，嚴格依序，不多不少。"""


def build_analyst_prompt(layer1: str, layer2: str, layer3: str,
                          layer4: str, knowledge_history: str,
                          market_data: str) -> str:
    ctx = ""
    if market_data:
        ctx += f"\n{market_data}\n"
    if layer1:
        ctx += f"\n### 昨日摘要\n{layer1}\n"
    if layer2:
        ctx += f"\n### 本週市場結構\n{layer2}\n"
    if layer3:
        ctx += f"\n### 現有 Thesis 清單\n{layer3}\n"
    if layer4:
        ctx += f"\n### 攻擊記錄\n{layer4}\n"
    if knowledge_history:
        ctx += f"\n### Knowledge Desk 近期主題（避免重複）\n{knowledge_history}\n"
    if ctx:
        ctx = f"\n---\n{ctx}\n---\n"

    if market_data:
        searches = f"""1. "geopolitics conflict diplomacy {DATE_STR}"
2. "central bank policy regulation fiscal {DATE_STR}"
3. "{PERIPHERY_QUERY}" """
    else:
        searches = f"""1. "markets SPX oil gold bonds {DATE_STR}"
2. "geopolitics macro policy {DATE_STR}"
3. "{PERIPHERY_QUERY}" """

    return f"""{DATE_LABEL} 情報草稿。

3次搜尋（依序，不多不少）：
{searches}
{ctx}
草稿結構：

## 資產快照
Brent、10Y UST、DXY、SPX、Gold（使用預載數據 + 搜尋脈絡解讀）。

## 核心事件
1-2 個 highest-impact 事件走完整 So What 鏈。
每個判斷後加【攻擊結果】（五種攻擊）。
攻擊後若改變判斷，標注修正版本。

## 邊陲：{PERIPHERY_LABEL}
局勢、行為者、與全球宏觀的傳導路徑。

## Knowledge Desk 素材
1個概念（避免與近期主題重複）：
- 概念名稱與難度層級（concept / mechanism / structural）
- 為何今天重要、歷史案例（附年份數據）、常見誤解、何時失效

## 前瞻訊號
48-72hr 內 3-5 個關鍵 catalysts，每個附影響路徑。

## 資產方向
各資產方向、理由、conviction（H/M/L）、主要風險。

（若有 thesis 變動，末尾標記。）"""

# ── Logic Guardrail ───────────────────────────────────────────────────────────
def perform_logic_guardrail(analyst_draft: str, hard_truths: dict) -> str:
    """Uses a fast model to check if Analyst draft contradicts Python-calculated hard truths."""
    if not hard_truths:
        return ""
    
    check_prompt = f"""你是一個嚴格的數據審核員。
以下是今日的「硬核數據事實」：
{json.dumps(hard_truths, indent=2)}

以下是分析師寫的「情報草稿」：
---
{analyst_draft}
---

請檢查草稿中是否有任何描述與數據事實直接衝突？
特別檢查：
1. 實質利率 (Real Yield) 的變動方向是否正確？
2. 殖利率曲線是否誤報？

若有衝突，請簡潔指出錯誤，並給出正確的描述。若無衝突，請回覆「PASS」。
只輸出結論，不要解釋。"""

    try:
        result = call_claude(
            "你只輸出數據校驗結果。若無誤回覆 PASS，若有誤指出錯誤點。",
            check_prompt,
            MODEL_HAIKU,
            max_tokens=300
        )
        if "PASS" in result.upper():
            return ""
        return f"\n\n【數據校驗警告 (Data Guardrail Warning)】：\n{result}\n請在最終敘事中修正上述數據矛盾。"
    except Exception as e:
        print(f"    ⚠ Guardrail failed: {e}")
        return ""

# ── Narrator ──────────────────────────────────────────────────────────────────
NARRATOR_SYSTEM = """你是宏觀對沖基金的說書人兼導師（The Narrator）。

你同時是三個角色：
- 策略師：分析轉譯成判斷和方向
- 老師：引導讀者思考，不給答案
- 說書人：讓複雜的事有節奏有張力

讀者：政治學背景，志在金融，已有分析肌肉，缺實戰練習量。
目標：15-20分鐘閱讀，每個字都有存在的理由。
核心原則：幫讀者建立自己的分析框架，不是餵結論。

【敘事紀律（Show, Don't Tell）】：
絕對禁止使用「根據攻擊框架」、「替代解讀為」、「修正後的判斷」、「引入反身性思考」等後設（Meta）描述詞彙。
必須將這些視角無縫內化為你本人的獨立思考。請直接使用「然而，我們必須質疑...」、「但若從倉位出清的角度來看...」、「市場可能忽略的盲區是...」來引導轉折。讀者不該知道你有一個「攻擊清單」。

特別要求：
- 若今日資產方向與昨日不同，必須用一句話說明變化原因
- Risk Map 每個風險附主觀機率區間
- conviction 標籤必須嚴格為以下三種字串之一，一字不漏，禁止擅自修改括號內的機率數字：
  H (65-80%)
  M (55-65%)
  L (45-55%)

格式規則：
- 繁體中文，保留英文術語
- 禁止 Markdown 表格、emoji（🔴🟠🟡除外）
- 直接輸出報告，不要開場白
- ## 標題，### 子標題
- 段落2-3句連貫，bullet 用 -
- 破折號（——）只用於強調
- 重要時間標注台灣時間"""


def build_narrator_prompt(analyst_draft: str, guardrail_warning: str = "") -> str:
    warning_block = ""
    if guardrail_warning:
        warning_block = f"\n\n!!! 重要修正指令 !!!\n{guardrail_warning}\n在輸出報告時，請務必採納上述修正，確保敘事與數據事實一致。"

    return f"""整合以下草稿（含【攻擊結果】），輸出最終報告。{warning_block}
把攻擊結果的內容自然融入敘事，展現分析的複雜性，不要另起段落標注。
若攻擊導致了 thesis 修正，在敘事中體現修正後的判斷。

=== 草稿 ===
{analyst_draft}

嚴格8段結構：

# Daily Intelligence Brief
{DATE_LABEL} | Strategy & Political Economy Desk

---

## 一、今日張力
一句話核心矛盾——讓讀者帶著問題讀完報告的引子。

---

## 二、數據切面
5條（Brent、10Y UST、DXY、SPX、Gold）：
- **指標（縮寫）**（中文）數值 ↑/↓ — 一句意義 + 隱含定價判讀

---

## 三、今日主線
最重要的一個事件或結構。說書人風格，起承轉合。
包含完整 So What 鏈，自然融入攻擊結果的複雜性。
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
第二段：與今日主線的傳導路徑（資金流、供應鏈、政治聯盟）。[重要警告]：若邊陲的長期結構（如氣候、人口）與今日主線（短期價格波動）無實質的因果傳導，請明確指出兩者的「脫鉤（Decoupling）」或「市場資金的錯配」，絕對禁止牽強附會地硬湊因果關係。

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


def parse_layer_update(raw: str, old_l2: str, old_kh: str,
                        report_summary: str) -> tuple[str, str, str, str]:
    raw = raw.strip()
    # 使用 \x60 防彈替代方案，避免 Markdown 解析器在複製貼上時出錯
    raw = re.sub(r"^\x60\x60\x60(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?\s*\x60\x60\x60$", "", raw)
    raw = raw.strip()

    try:
        data = json.loads(raw)
        l2 = data.get("layer2", "")
        l3_raw = data.get("layer3", [])
        l4_raw = data.get("layer4", [])
        l3 = json.dumps(l3_raw, ensure_ascii=False, indent=2) if isinstance(l3_raw, list) else str(l3_raw)
        l4 = json.dumps(l4_raw, ensure_ascii=False, indent=2) if isinstance(l4_raw, list) else str(l4_raw)
        kt = data.get("knowledge_topic", "")
        if l2:
            return l2, l3, l4, kt
    except json.JSONDecodeError as e:
        print(f"    ⚠ JSON parse failed: {e}")

    print("    → Fallback: appending today to L2")
    today_entry = f"{DATE_STR}：{report_summary[:100]}"
    if old_l2:
        cutoff = (TODAY - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        lines  = old_l2.strip().split("\n")
        kept   = [ln for ln in lines
                  if not re.match(r"^\d{4}-\d{2}-\d{2}", ln) or ln[:10] >= cutoff]
        kept.append(today_entry)
        return "\n".join(kept), "", "", ""
    return today_entry, "", "", ""

def build_layer_update_prompt(report_summary: str, analyst_draft: str,
                               old_l2: str, old_l3: str, old_l4: str,
                               old_kh: str) -> str:
    thesis_signals = "\n".join(
        line.strip() for line in analyst_draft.split("\n")
        if "NEW_THESIS:" in line or "INVALIDATE_THESIS:" in line
    ) or "（今日無新 thesis）"

    return f"""更新記憶層。輸出純 JSON（無 markdown）：

{{"layer2": "更新後 L2 文字", "layer3": [...], "layer4": [...], "knowledge_topic": "主題名稱"}}

今日摘要（{DATE_STR}）：
{report_summary}

Thesis 訊號：
{thesis_signals}

現有 L2（7天每日壓縮）：
{old_l2 or "（空）"}

現有 L3（thesis JSON 清單）：
{old_l3 or "[]"}

現有 L4（攻擊記錄）：
{old_l4 or "[]"}

規則：
L2：末尾加今日條目（嚴格格式）：
{DATE_STR}
regime: [當前市場 regime]
driver: [今日最主要價格驅動力]
policy: [Fed/主要央行偏向]
fragility: [最脆弱的資產或市場節點]
刪除 >7天的條目。

L3：JSON 陣列，格式：{{"name":"...","statement":"...","date":"...","assets":[...],"invalidators":[...],"status":"active"}}
- 加入 NEW_THESIS，將 INVALIDATE_THESIS 的 status 改為 "invalidated"
- 刪除 >30天且 status=invalidated 的項目

L4：JSON 陣列，格式：{{"date":"...","attack_type":"...","description":"...","thesis_revised":true/false}}
- attack_type：regime_misclassification / timing_error / reflexivity_break / second_order_inversion / omitted_variable_bias
- 加入今日最重要的 1 條，刪除 >14天的項目"""

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
    """Analyst with web search + extended thinking on Sonnet."""
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

    return "\n".join([b.text for b in response.content if hasattr(b, "text")])


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
    page_id = find_or_create_memo(title)
    data    = notion_get(f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100")
    old_ids = [b["id"] for b in data.get("results", [])]
    append_blocks(page_id, new_content)
    for block_id in old_ids:
        try:
            notion_delete(f"https://api.notion.com/v1/blocks/{block_id}")
        except Exception as e:
            print(f"    ⚠ Could not delete old block {block_id}: {e}")

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


def update_knowledge_history(old_kh: str, new_topic: str) -> str:
    if not new_topic:
        return old_kh
    entries = [ln.strip() for ln in old_kh.strip().split("\n") if ln.strip()] if old_kh else []
    entries.append(f"{DATE_STR}: {new_topic}")
    return "\n".join(entries[-10:])

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{DATE_STR}] Daily Intelligence Brief v8.2 — {PERIPHERY_LABEL}")
    print(f"  Analyst/Narrator/Weekly: {MODEL_SONNET} | Layer: {MODEL_HAIKU}")

    # ── 0. Market data (free APIs) ────────────────────────────────────────────
    print("  → Market data (yfinance + FRED + Correlation Matrix)...")
    yfd, corr_text = fetch_yfinance_data()
    frd = fetch_fred_data()
    market_data, hard_truths = format_market_data(yfd, frd, corr_text)
    if market_data:
        print(f"    ✓ yf:{len(yfd)} indicators | fred:{len(frd)} indicators | Correlation Matrix: {'✓' if corr_text else '∅'}")
    else:
        print("    ⚠ APIs unavailable → search 1 reverts to market data query")

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

    # ── 2. Analyst + DA (Sonnet + extended thinking, 3 searches) ──────────────
    print("  → [Analyst+DA] Draft (Sonnet + extended thinking, 3 searches)...")
    analyst_draft = with_retry(
        call_claude_with_search,
        ANALYST_SYSTEM,
        build_analyst_prompt(layer1, layer2, layer3, layer4, knowledge_history, market_data),
    )
    print(f"  ✓ Draft ({len(analyst_draft)} chars)")
    
    # ── 2.5 Logic Guardrail (Data Consistency Check) ─────────────────────────
    print("  → [Guardrail] Verifying macro logic...")
    guardrail_warning = perform_logic_guardrail(analyst_draft, hard_truths)
    if guardrail_warning:
        print("    ⚠ Logic violation detected! Correction injected.")
    else:
        print("    ✓ Logic check passed.")

    # ── 3. Narrator (Sonnet) ──────────────────────────────────────────────────
    print("  → [Narrator] Final report (Sonnet)...")
    final_report = with_retry(
        call_claude,
        NARRATOR_SYSTEM,
        build_narrator_prompt(analyst_draft, guardrail_warning),
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
        if new_l3:
            safe_overwrite_memo(LAYER3_TITLE, new_l3)
        if new_l4:
            safe_overwrite_memo(LAYER4_TITLE, new_l4)
        updated_kh = update_knowledge_history(knowledge_history, new_kt)
        if updated_kh:
            safe_overwrite_memo(KNOWLEDGE_HISTORY, updated_kh)
        print(f"  ✓ Memory (L2={'✓' if new_l2 else '∅'} "
              f"L3={'✓' if new_l3 else '∅'} L4={'✓' if new_l4 else '∅'} "
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
