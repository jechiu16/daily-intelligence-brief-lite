"""
Daily Intelligence Brief Generator — v8.3

Architecture:
  - Data layer: yfinance + FRED + Correlation Matrix
  - Analyst + DA (Sonnet + extended thinking, 3 narrative searches)
  - Logic Guardrail (Haiku — hard data consistency check)
  - Opus Logic Chain Reviewer (causal + historical fact check)
  - Narrator (Sonnet — 通識課教授角色)
  - Post-Narrator Data Audit (Haiku — catches Narrator drift)
  - Layer Update (Haiku)
  - Weekly Review (Sonnet)

v8.3 fixes (from live audit):
  1. hard_truths expanded: all assets now include price, direction, pct
  2. Guardrail scope widened: checks every asset's price/direction/pct, not just real yield
  3. Post-Narrator audit: second guardrail AFTER Narrator rewrites, catches drift
  4. Data anchors injected into Narrator prompt as immutable reference
  5. Correlation matrix label fixed: was "近5日", actually uses 20-day window
  6. Opus Logic Reviewer now checks historical fact accuracy (year/event matching)
  7. Market data labels clarified as closing prices with intraday note
  8. build_narrator_prompt accepts hard_truths for data anchor injection

Deployment:
  pip install anthropic httpx pandas numpy yfinance fredapi tzdata
  GitHub Secrets: ANTHROPIC_API_KEY, NOTION_API_KEY,
                  NOTION_DATABASE_ID, NOTION_WEEKLY_DB_ID, FRED_API_KEY
"""

import os
import re
import json
import time
import datetime
import anthropic
import httpx
import pandas as pd
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Asia/Taipei")

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY    = os.environ["NOTION_API_KEY"]
NOTION_DB_ID      = os.environ["NOTION_DATABASE_ID"]
NOTION_WEEKLY_DB  = os.environ.get("NOTION_WEEKLY_DB_ID", NOTION_DB_ID)
FRED_API_KEY      = os.environ.get("FRED_API_KEY", "")

MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU  = "claude-haiku-4-5-20251001"
MODEL_OPUS   = "claude-opus-4-6"

TODAY     = datetime.datetime.now(_TZ).date()
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
        "SPX":    "^GSPC",
        "Brent":  "BZ=F",
        "Gold":   "GC=F",
        "DXY":    "DX-Y.NYB",
        "UST10Y": "^TNX",
        "VIX":    "^VIX",
    }
    results = {}
    corr_text = ""
    try:
        data = yf.download(list(tickers.values()), period="10d", interval="1d",
                           progress=False, threads=True)
        if data.empty:
            return {}, ""

        close = data["Close"]

        # ── Correlation matrix (20-day window) ────────────────────────────
        # v8.3 fix: label now correctly says 20日, matching actual window
        try:
            subset = close[list(tickers.values())].tail(20)
            inv = {v: k for k, v in tickers.items()}
            subset.columns = [inv.get(c, c) for c in subset.columns]
            corr = subset.corr()
            lines = ["### 資產相關性矩陣（近20個交易日）",
                     "1.0=完全正相關，-1.0=完全負相關"]
            header = "     | " + " | ".join(f"{c:>6}" for c in corr.columns)
            lines.append(header)
            for idx, row in corr.iterrows():
                lines.append(f"{idx:5} | " + " | ".join(f"{v:+.2f}" for v in row))
            corr_text = "\n".join(lines) + "\n"
        except Exception as e:
            print(f"    ⚠ Correlation: {e}")

        for name, tk in tickers.items():
            try:
                s = close[tk].dropna()
                if len(s) >= 2:
                    lat, prev = float(s.iloc[-1]), float(s.iloc[-2])
                    results[name] = {
                        "price":  round(lat, 2),
                        "change": round(lat - prev, 2),
                        "pct":    round((lat - prev) / prev * 100, 2),
                        "date":   str(s.index[-1].date()),
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
        fred  = Fred(api_key=FRED_API_KEY)
        start = YESTERDAY - datetime.timedelta(days=10)
        for name, sid in series.items():
            try:
                s = fred.get_series(sid, observation_start=start).dropna()
                if len(s) >= 2:
                    lat, prev = float(s.iloc[-1]), float(s.iloc[-2])
                    results[name] = {
                        "value":  round(lat, 3),
                        "prev":   round(prev, 3),
                        "change": round(lat - prev, 3),
                        "date":   str(s.index[-1].date()),
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
    """Returns (market_data_string, hard_truths_dict).
    v8.3: hard_truths now includes ALL asset prices, directions, and pct changes."""
    if not yfd and not frd:
        return "", {}

    hard_truths = {}
    lines = ["## 預載市場數據（API 直取，精確度高於搜尋）\n"]

    if corr_text:
        lines.append(corr_text + "\n")

    # ── v8.3: Asset data with closing price labels + inject ALL into hard_truths ──
    if yfd:
        lines.append("### 價格（yfinance，收盤價）")
        for n, d in yfd.items():
            if d["change"] is not None:
                dr = "↑" if d["change"] > 0 else "↓" if d["change"] < 0 else "→"
                lines.append(f"- {n}: {d['price']}（收盤價）({dr} {d['pct']:+.2f}%) [{d['date']}]")
                # v8.3: populate hard_truths for every asset
                hard_truths[f"{n}_price"] = d["price"]
                hard_truths[f"{n}_pct"] = d["pct"]
                hard_truths[f"{n}_direction"] = (
                    "up" if d["change"] > 0 else "down" if d["change"] < 0 else "flat"
                )
            else:
                lines.append(f"- {n}: {d['price']}（收盤價）[{d['date']}]")
                hard_truths[f"{n}_price"] = d["price"]
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

        lines.append("### 衍生訊號（Python 硬核計算）")
        yc  = frd.get("Yield Curve (10Y-2Y)", {})
        be  = frd.get("Breakeven Inflation", {})
        hy  = frd.get("HY Credit Spread", {})
        n10 = frd.get("10Y Treasury", {})

        if yc.get("value") is not None:
            v   = yc["value"]
            tag = "倒掛（衰退訊號）" if v < 0 else "平坦（成長前景謹慎）" if v < 0.5 else "正常"
            lines.append(f"- 殖利率曲線 (10Y-2Y)：{v}% — {tag}")
            hard_truths["yield_curve_value"]    = v
            hard_truths["yield_curve_inverted"] = v < 0

        # Real Yield = Nominal 10Y - Breakeven (Python-computed)
        if n10.get("value") is not None and be.get("value") is not None:
            ry_today = round(n10["value"] - be["value"], 3)
            hard_truths["real_yield_value"] = ry_today

            ry_direction = "flat"
            if n10.get("prev") is not None and be.get("prev") is not None:
                ry_prev      = round(n10["prev"] - be["prev"], 3)
                delta        = ry_today - ry_prev
                ry_direction = "up" if delta > 0.001 else "down" if delta < -0.001 else "flat"
            hard_truths["real_yield_direction"] = ry_direction

            dr_label = {"up": "↑", "down": "↓", "flat": "→"}[ry_direction]
            lines.append(
                f"- 實質利率 (10Y Real Yield)：{ry_today}% ({dr_label})"
                f"  [= Nominal {n10['value']}% − BEI {be['value']}%]"
            )

        if be.get("value") is not None:
            v   = be["value"]
            tag = "高於" if v > 2.5 else "接近" if v > 2.0 else "低於"
            lines.append(f"- 通膨預期（10Y BEI）：{v}% — {tag} Fed 目標")
            hard_truths["breakeven_value"] = v

        if hy.get("value") is not None:
            v   = hy["value"]
            tag = "壓力區間" if v > 5.0 else "偏緊" if v < 3.5 else "正常"
            lines.append(f"- 高收益信用利差：{v}% — {tag}")
            hard_truths["hy_spread_value"] = v
        lines.append("")

    # v8.3: clarified closing price note + intraday warning
    lines.append(
        "（直接使用以上數據，不需再搜尋驗證。"
        "若敘事與數據計算衝突，以數據為準。\n"
        "注意：以上為收盤價。若搜尋結果顯示盤中價格與收盤價有顯著差異，"
        "請在報告中標注盤中波動，但方向性判斷與漲跌幅以收盤價為準。）\n"
    )
    return "\n".join(lines), hard_truths

# ── Analyst + Devil's Advocate ────────────────────────────────────────────────
ANALYST_SYSTEM = """你是全球宏觀對沖基金的情報分析師兼首席風險官。

重要：若收到預載市場數據（yfinance + FRED），直接使用，不需搜尋市場價格。3次 web_search 全部用於敘事性搜尋。

【絕對宏觀法則（Macro Physics Engine）】
在推導跨資產邏輯時，必須嚴格遵守以下數學與金融常理，絕不可為了敘事流暢而扭曲：
1. 實質殖利率 = 名目殖利率 − 通膨預期（BEI）。若原物料大跌導致通膨預期重挫而名目殖利率跌幅較小，實質殖利率為「上升（Spike）」。
2. 實質殖利率上升 → 壓縮高估值資產（SPX 科技股）的估值倍數。
3. 若市場出現背離（實質利率升、美股卻大漲），必須定調為「倉位回補」或「流動性幻覺」，切勿合理化為基本面改善。
Python 已預先計算實質利率，數字在預載數據中，請直接引用。

【數據精確度法則（v8.3 新增）】
- 預載數據中的價格、漲跌幅、方向是 Python 從 API 直取的收盤價，精確度最高。
- 搜尋結果中的價格可能是盤中快照、開盤價、或不同時區的報價，與收盤價可能有差異。
- 若搜尋價格與預載數據衝突：方向與幅度以預載數據為準，但可在文中補充盤中波動描述。
- 禁止對預載數據做四捨五入或「記憶性改寫」——引用時必須逐字使用預載數字。

分析規則：
- 1-2 個 highest-impact 事件走完整 So What 鏈：事實（數據）→ 經濟機制 → 誰得利/受損 → 風險定價狀態（已定價/部分定價/未定價/過度定價）→ 二階效應 → 資產影響
- 每個核心判斷後執行五種結構化攻擊，標記為【攻擊結果】：
  1. regime_misclassification — 若 regime 判斷錯誤，最可能的替代解讀？
  2. timing_error — 方向正確但時機錯誤的條件？
  3. reflexivity_break — 倉位擁擠是否讓 thesis 失效？
  4. second_order_inversion — 因果鏈在什麼條件下反轉？
  5. omitted_variable_bias — 因果鏈正確但有哪個隱藏變數被忽略？
  攻擊後：若改變判斷，標注修正後版本。
- 記錄反向訊號

【歷史案例精確度法則（v8.3 新增）】
引用歷史案例時：
- 年份必須準確。若不確定，用搜尋驗證或標注「約 XXXX 年」。
- 禁止混淆不同事件的時間線（例：紅海危機是 2023-2024 年，不是 2022 年）。
- 每個歷史案例必須附帶至少一個可驗證的數據點（指數水平、利率、跌幅等）。

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

    searches = (
        f"""1. "geopolitics conflict diplomacy {DATE_STR}"
2. "central bank policy regulation fiscal {DATE_STR}"
3. "{PERIPHERY_QUERY}" """
        if market_data else
        f"""1. "markets SPX oil gold bonds {DATE_STR}"
2. "geopolitics macro policy {DATE_STR}"
3. "{PERIPHERY_QUERY}" """
    )

    return f"""{DATE_LABEL} 情報草稿。

3次搜尋（依序，不多不少）：
{searches}
{ctx}
草稿結構：

## 資產快照
Brent、10Y UST、DXY、SPX、Gold（使用預載數據 + 搜尋脈絡解讀）。
【重要】引用價格和漲跌幅時，必須逐字使用預載數據中的數字，不得四捨五入或從搜尋結果取替代數字。

## 核心事件
1-2 個 highest-impact 事件走完整 So What 鏈。
每個判斷後加【攻擊結果】（五種攻擊）。
攻擊後若改變判斷，標注修正版本。

## 邊陲：{PERIPHERY_LABEL}
局勢、行為者、與全球宏觀的傳導路徑。

## Knowledge Desk 素材
1個概念（避免與近期主題重複）：
- 概念名稱與難度層級（concept / mechanism / structural）
- 為何今天重要、歷史案例（附年份數據，年份必須準確）、常見誤解、何時失效

## 前瞻訊號
48-72hr 內 3-5 個關鍵 catalysts，每個附影響路徑。

## 資產方向
各資產方向、理由、conviction（H/M/L）、主要風險。

（若有 thesis 變動，末尾標記。）"""

# ── Logic Guardrail (v8.3: expanded scope) ────────────────────────────────────
def perform_logic_guardrail(text: str, hard_truths: dict, stage: str = "analyst") -> str:
    """Haiku cross-checks text against Python-computed hard_truths.
    v8.3: now checks ALL asset prices, directions, and pct — not just real yield.
    stage: 'analyst' or 'narrator' for clearer error messages.
    Returns empty string if PASS, or a correction warning string."""
    if not hard_truths:
        return ""

    # Build a human-readable checklist from hard_truths
    checks = []
    asset_names = ["SPX", "Brent", "Gold", "DXY", "UST10Y", "VIX"]
    for asset in asset_names:
        price_key = f"{asset}_price"
        pct_key = f"{asset}_pct"
        dir_key = f"{asset}_direction"
        if price_key in hard_truths:
            checks.append(
                f"- {asset}: 收盤價={hard_truths[price_key]}, "
                f"漲跌幅={hard_truths.get(pct_key, 'N/A')}%, "
                f"方向={hard_truths.get(dir_key, 'N/A')}"
            )

    if hard_truths.get("real_yield_value") is not None:
        checks.append(
            f"- 實質利率: {hard_truths['real_yield_value']}%, "
            f"方向={hard_truths.get('real_yield_direction', 'N/A')}"
        )
    if hard_truths.get("yield_curve_inverted") is not None:
        checks.append(
            f"- 殖利率曲線: 倒掛={'是' if hard_truths['yield_curve_inverted'] else '否'}, "
            f"值={hard_truths.get('yield_curve_value', 'N/A')}%"
        )
    if hard_truths.get("breakeven_value") is not None:
        checks.append(f"- BEI: {hard_truths['breakeven_value']}%")
    if hard_truths.get("hy_spread_value") is not None:
        checks.append(f"- HY Spread: {hard_truths['hy_spread_value']}%")

    checks_text = "\n".join(checks)

    check_prompt = f"""你是嚴格的數據審核員。以下是 Python 直接從 API 計算的精確數據：

{checks_text}

以下是待審核的{stage}文本：
---
{text[:4000]}
---

逐項檢查：
1. 文本中每個資產（SPX, Brent, Gold, DXY, VIX）的漲跌方向是否與數據一致？
2. 文本中的漲跌幅數字是否與數據偏差超過 1.5 個百分點？
3. 文本中的價格數字是否與數據偏差超過 2%？
4. 實質利率方向描述是否與 real_yield_direction 一致？
5. 殖利率曲線形態描述是否與 yield_curve_inverted 一致？

若全部正確，回覆：PASS
若有衝突，逐條列出錯誤：[資產/指標] 文本說 [X]，但數據顯示 [Y]。
只輸出結論，不要解釋。"""

    try:
        result = call_claude(
            "你只輸出數據校驗結果。若無誤回覆 PASS，若有誤逐條列出錯誤。",
            check_prompt,
            MODEL_HAIKU,
            max_tokens=400,
        )
        if "PASS" in result.upper() and "不" not in result and "錯" not in result:
            return ""
        return f"\n\n【{stage}數據校驗警告】：{result.strip()}\n請在最終敘事中修正此數據矛盾。"
    except Exception as e:
        print(f"    ⚠ Guardrail ({stage}) failed: {e}")
        return ""

# ── Opus Logic Chain Reviewer (v8.3: + historical fact check) ────────────────
LOGIC_REVIEWER_SYSTEM = """你是全球頂尖宏觀對沖基金的首席邏輯審查官（Chief Logic Reviewer）。

任務：審查情報草稿的邏輯鏈縝密性。不搜尋，不寫作，只挑剔。

審查標準：
1. 因果跳躍：A → B 之間缺少關鍵的傳導機制（例：「油價跌→美股漲」，跳過了實質利率、企業成本、消費者信心的中間步驟）
2. 結論超出數據：草稿的判斷強度超過數據所能支撐的範圍
3. 時間框架混淆：把短期市場信號當作長期結構判斷，或反之
4. 缺失的反向論證：核心判斷缺少最強的反方論點
5. 循環論證：用結論來支撐前提
6. 歷史事實錯位（v8.3 新增）：草稿引用的歷史案例，年份與事件是否匹配？
   已知容易混淆的案例：
   - 紅海航運危機（胡塞武裝攻擊商船）：2023年底至2024年，不是2022年
   - 俄烏戰爭油價衝擊：2022年
   - SVB 銀行危機：2023年3月
   - 日圓干預：2022年9-10月、2024年4-5月
   若草稿引用的歷史案例年份可疑，必須標記。

輸出格式：
若邏輯鏈完整且歷史事實無誤，輸出：PASS
若有問題，列出 2-4 個最重要的缺陷，每條格式：
[問題類型] 具體描述（引用草稿原句）→ 建議如何修正

只輸出審查結果，不要開場白，不要解釋你的工作方式。"""


def perform_logic_review(analyst_draft: str) -> str:
    """Opus deep logic chain review. Returns empty string if PASS."""
    review_prompt = f"""以下是今日情報草稿，請審查邏輯鏈縝密性與歷史事實準確性：

---
{analyst_draft}
---

依審查標準輸出結果。若無問題輸出 PASS。"""

    try:
        result = call_claude(
            LOGIC_REVIEWER_SYSTEM,
            review_prompt,
            MODEL_OPUS,
            max_tokens=800,
        )
        result = result.strip()
        if result.upper().startswith("PASS"):
            return ""
        return result
    except Exception as e:
        print(f"    ⚠ Logic review failed: {e}")
        return ""


# ── Narrator（通識課教授）────────────────────────────────────────────────────
NARRATOR_SYSTEM = """你是一位宏觀對沖基金出身、橫跨金融與國際政治的複合型分析師。

你的三重身份，各司其職：
- 策略師：把數據和事件翻譯成可執行的方向判斷。配置羅盤、前瞻監控、conviction 是你的語言。
- 國際關係學者：用權力結構、制度邏輯、歷史類比解讀今日事件。今日主線、邊陲訊號的地理邏輯是你的主場。
- 知識領路人：幫讀者找到概念在知識地圖上的位置——這個工具在哪裡成立、在哪個框架下會被質疑。Knowledge Desk 和思考題是你的主場。

讀者：政治學背景的學生，志在金融，已有分析肌肉，缺乏實戰練習量。
目標：讓他讀完這份報告後，今天看世界的方式跟昨天不一樣。15-20分鐘。
核心原則：這份報告的目的是幫讀者建立自己的分析框架，不是替他下結論。

【敘事紀律（Show, Don't Tell）】
絕對禁止的後設語彙：「根據攻擊框架」、「替代解讀為」、「修正後的判斷」、「引入反身性思考」、「根據五種攻擊」。
批判性視角必須作為你自己的思考無縫呈現：
  ✓ 「然而，我們必須質疑...」
  ✓ 「但若從倉位出清的角度來看...」
  ✓ 「市場可能忽略的盲區是...」
讀者不應該知道你有一份攻擊清單。

【數據精確度法則（v8.3 新增）】
你將收到一份「數據錨點」，包含所有資產的精確收盤價、漲跌幅、方向。
- 報告中出現的所有價格和百分比必須與數據錨點完全一致，逐字引用，不得修改。
- 不得對數據做四捨五入、記憶性改寫、或從其他來源取替代數字。
- 若盤中走勢與收盤數據有顯著差異，可在敘事中補充盤中描述，但數據切面必須使用收盤數字。

特別要求：
- 若今日資產方向與昨日不同，必須用一句話說明變化原因
- Risk Map 每個風險附主觀機率區間
- conviction 標籤必須嚴格為以下三種格式之一，一字不漏：
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


def build_narrator_prompt(analyst_draft: str, hard_truths: dict,
                           guardrail_warning: str = "", logic_review: str = "") -> str:
    """v8.3: now accepts hard_truths and injects as immutable data anchors."""

    # ── Data anchor injection ─────────────────────────────────────────────
    data_anchor = ""
    if hard_truths:
        anchor_lines = ["!!! 數據錨點（不可修改，必須逐字引用）!!!"]
        asset_names = ["SPX", "Brent", "Gold", "DXY", "UST10Y", "VIX"]
        for asset in asset_names:
            price = hard_truths.get(f"{asset}_price")
            pct = hard_truths.get(f"{asset}_pct")
            direction = hard_truths.get(f"{asset}_direction")
            if price is not None:
                dir_arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(direction, "?")
                pct_str = f"{pct:+.2f}%" if pct is not None else "N/A"
                anchor_lines.append(f"- {asset}: {price} ({dir_arrow} {pct_str})")

        ry = hard_truths.get("real_yield_value")
        ry_dir = hard_truths.get("real_yield_direction")
        if ry is not None:
            anchor_lines.append(f"- 實質利率: {ry}% (方向: {ry_dir})")
        bei = hard_truths.get("breakeven_value")
        if bei is not None:
            anchor_lines.append(f"- BEI: {bei}%")
        hy = hard_truths.get("hy_spread_value")
        if hy is not None:
            anchor_lines.append(f"- HY Spread: {hy}%")

        anchor_lines.append(
            "\n報告「二、數據切面」中的所有數字必須與上述錨點完全一致。"
            "敘事中引用價格或漲跌幅時，也必須使用錨點數字，不得修改。"
        )
        data_anchor = "\n".join(anchor_lines)

    # ── Correction injections ─────────────────────────────────────────────
    correction = ""
    if data_anchor:
        correction += f"\n\n{data_anchor}\n"
    if guardrail_warning:
        correction += (
            f"\n\n!!! 數據修正指令 !!!\n{guardrail_warning}\n"
            "輸出報告時必須採納此修正，確保敘事與數據一致。"
        )
    if logic_review:
        correction += (
            f"\n\n!!! 邏輯鏈修正指令（Opus 審查結果）!!!\n{logic_review}\n"
            "以下邏輯缺陷必須在最終報告中修正或補強，不得保留原有的邏輯跳躍。"
        )

    return f"""整合以下草稿（含【攻擊結果】），輸出最終報告。{correction}
把攻擊結果無縫融入敘事，嚴守【敘事紀律】，讀者不應知道有攻擊清單。
若攻擊導致 thesis 修正，在敘事中直接體現修正後的判斷。

=== 草稿 ===
{analyst_draft}

嚴格8段結構：

# Daily Intelligence Brief
{DATE_LABEL} | Strategy & Political Economy Desk

---

## 一、今日張力
一句話核心矛盾——讓讀者帶著這個問題讀完報告。

---

## 二、數據切面
5條（Brent、10Y UST、DXY、SPX、Gold）：
- **指標（縮寫）**（中文）數值 ↑/↓ — 一句意義 + 隱含定價判讀
【重要】所有數字必須與數據錨點完全一致，逐字引用。

---

## 三、今日主線
最重要的一個事件或結構。教授講課的風格：有起承轉合，有反問，有留白。
包含完整 So What 鏈，自然融入攻擊結果的複雜性。
若方向與昨日不同，說明變化原因。1000字內。

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
第二段：與今日主線的傳導路徑。
【重要】：若邊陲的長期結構與今日短期市場波動無實質因果傳導，請明確指出「脫鉤（Decoupling）」或「兩條平行線」。禁止硬湊因果。

---

## 六、配置羅盤

### 方向判斷
5條（美股、台股、美債、主要貨幣、黃金）：
- **資產（縮寫）↑/↓** — 邏輯 + conviction H/M/L（嚴格格式）

### 前瞻監控（48-72hr）
3-5個 catalysts：
- 事件（台灣時間）— 重要性 + 影響路徑

---

## 七、Knowledge Desk

### 概念：[名稱]
**為什麼今天重要**：一句話連結今日報告。
**實戰應用**：這個概念在配置決策中怎麼用？什麼條件下失效？典型的錯誤理解是什麼？2-3段，教授口吻，有問題，有留白。
**歷史案例**：一個真實案例，附年份與結果。年份必須準確。
**當前關鍵問題**：基於今日環境，最值得追蹤的一個開放性問題。

---

## 八、今日思考題
一個開放性問題，無標準答案。讓讀者帶著它觀察接下來幾天。
若昨日有思考題，先一句話回應其進展。

---
**資料來源**
1-3條：機構 — 標題，日期"""

# ── Layer Update (Haiku) ──────────────────────────────────────────────────────
LAYER_UPDATE_SYSTEM = """宏觀對沖基金資料管理員。輸出合法 JSON，不加說明或代碼塊。"""


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
    """Analyst with web search + extended thinking.
    Hard-validates that at least 3 searches complete before accepting end_turn."""
    client       = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages     = [{"role": "user", "content": user}]
    search_count = 0
    text_blocks  = []

    for _ in range(8):
        response = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=5000,
            thinking={"type": "enabled", "budget_tokens": 2000},
            system=system,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]

        # Count search calls in this turn
        for block in response.content:
            if hasattr(block, "type") and block.type == "tool_use":
                search_count += 1

        # Only accept end_turn after all 3 searches have fired
        if response.stop_reason == "end_turn" and search_count >= 3:
            return "\n".join(text_blocks)

        messages.append({"role": "assistant", "content": response.content})
        tool_results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": "Search executed."}
            for b in response.content if b.type == "tool_use"
        ]
        if not tool_results:
            # No more tool calls — graceful degradation
            if response.stop_reason == "end_turn" and search_count < 3:
                print(f"    ⚠ Search loop ended early: {search_count}/3 searches completed")
            return "\n".join(text_blocks)
        messages.append({"role": "user", "content": tool_results})

    return "\n".join(text_blocks)


def call_claude(system: str, user: str, model: str, max_tokens: int = 3000) -> str:
    client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
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
    resp.raise_for_status(); return resp.json()

def notion_patch(url: str, payload: dict) -> dict:
    resp = with_retry(httpx.patch, url, headers=NOTION_HEADERS, json=payload, timeout=TIMEOUT)
    resp.raise_for_status(); return resp.json()

def notion_get(url: str) -> dict:
    resp = with_retry(httpx.get, url, headers=NOTION_HEADERS, timeout=TIMEOUT)
    resp.raise_for_status(); return resp.json()

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
        notion_patch(f"https://api.notion.com/v1/blocks/{page_id}/children",
                     {"children": blocks[i:i+100]})


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


def get_or_create_daily_page(db_id: str, date_str: str) -> str:
    """Idempotent: return existing daily page if already exists, else create."""
    data = notion_post(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        {"filter": {"and": [
            {"property": "Date",  "date":   {"equals": date_str}},
            {"property": "Type",  "select": {"equals": "Daily"}},
        ]}}
    )
    results = data.get("results", [])
    if results:
        page_id = results[0]["id"]
        print(f"    ↻ Existing daily page found — updating ({page_id})")
        existing = notion_get(
            f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
        )
        for block in existing.get("results", []):
            try:
                notion_delete(f"https://api.notion.com/v1/blocks/{block['id']}")
            except Exception:
                pass
        return page_id
    return create_page(db_id, f"📊 Daily Brief | {date_str}", "daily")


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


def _repair_json(raw: str) -> str:
    """Attempt to fix common LLM JSON errors before parsing."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?\s*```$", "", raw)
    raw = raw.strip()
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*]", "]", raw)
    raw = re.sub(r"//[^\n]*\n", "\n", raw)
    return raw.strip()


def parse_layer_update(raw: str, old_l2: str, old_kh: str,
                        report_summary: str) -> tuple[str, str, str, str]:
    raw = _repair_json(raw)
    try:
        data = json.loads(raw)
        l2   = data.get("layer2", "")
        l3_raw, l4_raw = data.get("layer3", []), data.get("layer4", [])
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


def update_knowledge_history(old_kh: str, new_topic: str) -> str:
    if not new_topic:
        return old_kh
    entries = [ln.strip() for ln in old_kh.strip().split("\n") if ln.strip()] if old_kh else []
    entries.append(f"{DATE_STR}: {new_topic}")
    return "\n".join(entries[-10:])

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{DATE_STR}] Daily Intelligence Brief v8.3 — {PERIPHERY_LABEL}")
    print(f"  Analyst/Narrator/Weekly: {MODEL_SONNET} | Logic Review: {MODEL_OPUS} | Layer/Guardrail: {MODEL_HAIKU}")

    # ── 0. Market data ────────────────────────────────────────────────────────
    print("  → Market data (yfinance + FRED + Correlation)...")
    yfd, corr_text = fetch_yfinance_data()
    frd            = fetch_fred_data()
    market_data, hard_truths = format_market_data(yfd, frd, corr_text)
    if market_data:
        print(f"    ✓ yf:{len(yfd)} | fred:{len(frd)} | corr:{'✓' if corr_text else '∅'} | hard_truths:{len(hard_truths)}")
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

    # ── 2. Analyst (Sonnet + extended thinking, 3 searches) ───────────────────
    print("  → [Analyst+DA] Draft (Sonnet + extended thinking, 3 searches)...")
    analyst_draft = with_retry(
        call_claude_with_search,
        ANALYST_SYSTEM,
        build_analyst_prompt(layer1, layer2, layer3, layer4, knowledge_history, market_data),
    )
    print(f"  ✓ Draft ({len(analyst_draft)} chars)")

    # ── 2.5 Logic Guardrail (Haiku) — checks Analyst draft ───────────────────
    print("  → [Guardrail] Pre-narrator data check (Haiku)...")
    guardrail_warning = perform_logic_guardrail(analyst_draft, hard_truths, stage="analyst")
    if guardrail_warning:
        print("    ⚠ Data inconsistency detected — correction injected into Narrator")
    else:
        print("    ✓ Pre-narrator data check passed")

    # ── 2.6 Logic Chain Review (Opus) ─────────────────────────────────────────
    print("  → [Logic Reviewer] Deep logic + historical fact check (Opus)...")
    logic_review = perform_logic_review(analyst_draft)
    if logic_review:
        print(f"    ⚠ Logic/fact issues found — injected into Narrator")
        print(f"    Preview: {logic_review[:200]}...")
    else:
        print("    ✓ Logic chain + historical fact review passed")

    # ── 3. Narrator (Sonnet) — with data anchors ─────────────────────────────
    print("  → [Narrator/Professor] Final report (Sonnet)...")
    final_report = with_retry(
        call_claude,
        NARRATOR_SYSTEM,
        build_narrator_prompt(analyst_draft, hard_truths, guardrail_warning, logic_review),
        MODEL_SONNET,
        max_tokens=5500,
    )
    print(f"  ✓ Report ({len(final_report)} chars)")

    # ── 3.5 Post-Narrator Data Audit (Haiku) — catches Narrator drift ────────
    print("  → [Post-Narrator Audit] Checking final report for data drift (Haiku)...")
    post_narrator_warning = perform_logic_guardrail(final_report, hard_truths, stage="narrator")
    if post_narrator_warning:
        print("    ⚠ Narrator drift detected — attempting patch...")
        # Re-run Narrator with explicit correction
        patch_prompt = (
            f"以下報告存在數據錯誤，請只修正數據錯誤的部分，其他內容保持不變。\n"
            f"{post_narrator_warning}\n\n"
            f"=== 原報告 ===\n{final_report}"
        )
        try:
            final_report = with_retry(
                call_claude,
                "你是數據校對員。只修正被標記的數據錯誤，其他內容一字不改地保留。輸出完整修正後報告。",
                patch_prompt,
                MODEL_SONNET,
                max_tokens=5500,
            )
            print("    ✓ Patch applied")
        except Exception as e:
            print(f"    ⚠ Patch failed ({e}) — publishing with warning")
            final_report = f"⚠ 數據校驗警告：部分數據可能有偏差，請交叉驗證。\n\n{final_report}"
    else:
        print("    ✓ Post-narrator audit passed — no drift")

    # ── 4. Push to Notion (idempotent) ────────────────────────────────────────
    print("  → Pushing to Notion...")
    page_id = get_or_create_daily_page(NOTION_DB_ID, DATE_STR)
    append_blocks(page_id, final_report)
    print(f"  ✓ Pushed (page: {page_id})")

    # ── 5. Update memory (Haiku) ──────────────────────────────────────────────
    print("  → Updating memory (Haiku)...")
    try:
        report_summary = final_report[:1000]
        update_raw = call_claude(
            LAYER_UPDATE_SYSTEM,
            build_layer_update_prompt(report_summary, analyst_draft,
                                      layer2, layer3, layer4, knowledge_history),
            MODEL_HAIKU,
            max_tokens=1200,
        )
        new_l2, new_l3, new_l4, new_kt = parse_layer_update(
            update_raw, layer2, knowledge_history, report_summary
        )
        if new_l2: safe_overwrite_memo(LAYER2_TITLE, new_l2)
        if new_l3: safe_overwrite_memo(LAYER3_TITLE, new_l3)
        if new_l4: safe_overwrite_memo(LAYER4_TITLE, new_l4)
        updated_kh = update_knowledge_history(knowledge_history, new_kt)
        if updated_kh: safe_overwrite_memo(KNOWLEDGE_HISTORY, updated_kh)
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
