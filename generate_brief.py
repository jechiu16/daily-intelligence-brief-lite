"""
Daily Intelligence Brief Generator — v8.4 "Evolvable System"

Architecture:
  Layer 0  — Deterministic math (yfinance + FRED + derived signals)
  Layer 0b — Relational guardrail (cross-asset consistency, Python rules)
  Layer 1  — Analyst + DA (Sonnet + extended thinking, 3 narrative searches)
  Layer 1b — Logic Guardrail (Haiku — hard data consistency)
  Layer 1c — Opus Logic Chain Reviewer (causal + historical fact check)
  Layer 2  — Narrator (Sonnet — 通識課教授)
  Layer 2b — Post-Narrator Data Audit (Haiku — catches drift)
  Layer 3  — Memory Update (Haiku — L2/L3/L4/KH)
  Layer 4  — Daily Scorecard (L5 — T+1 prediction backtest)
  Layer 5  — Weekly Review + Thesis Outcome Eval + Prompt Governance
  Layer 6  — Monthly Meta Review (scaffolding)

v8.4 new systems:
  1.  Daily Scorecard (L5): T+1 backtest of yesterday's direction calls
  2.  Thesis Outcome Tracking: L3 schema adds outcome/outcome_date/outcome_method
  3.  Relational Guardrail: Python cross-asset consistency rules (pre-Analyst)
  4.  New indicators: 5y5y forward inflation, Copper/Gold ratio, NFCI (weekly)
  5.  Feedback Loop: L5 scorecard + recent hit rate injected into Analyst context
  6.  base_rate_neglect: 6th attack mode in DA
  7.  Prompt Governance: version tracking, weekly drift section, change log
  8.  Conviction dampener: auto-downgrade if 7d hit rate < 55%
  9.  Weekly review enhanced: thesis outcome eval + prompt review section
  10. Monthly review scaffolding (1st of month)

Prompt version: v8.4.0
Change log:
  v8.3.0 → v8.4.0: Added L5 scorecard, relational guardrail, thesis outcomes,
                     feedback loop, prompt governance, 5y5y + Cu/Au indicators

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

PROMPT_VERSION = "v8.4.0"

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
IS_FIRST_OF_MONTH = TODAY.day == 1
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

# Memory page titles
LAYER2_TITLE      = "__WeeklyCompressed__"
LAYER3_TITLE      = "__LongTermTracker__"
LAYER4_TITLE      = "__DevilsAdvocateLog__"
KNOWLEDGE_HISTORY = "__KnowledgeHistory__"
SCORECARD_TITLE   = "__DailyScorecard__"       # v8.4: L5
PROMPT_LOG_TITLE  = "__PromptGovernanceLog__"   # v8.4: prompt change history

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

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 0 — DETERMINISTIC DATA
# ══════════════════════════════════════════════════════════════════════════════

def fetch_yfinance_data() -> tuple[dict, str]:
    try:
        import yfinance as yf
    except ImportError:
        print("    ⚠ yfinance not installed"); return {}, ""

    # v8.4: added Copper (HG=F) for Cu/Au ratio
    tickers = {
        "SPX":    "^GSPC",
        "Brent":  "BZ=F",
        "Gold":   "GC=F",
        "DXY":    "DX-Y.NYB",
        "UST10Y": "^TNX",
        "VIX":    "^VIX",
        "Copper": "HG=F",
    }
    results = {}
    corr_text = ""
    try:
        data = yf.download(list(tickers.values()), period="22d", interval="1d",
                           progress=False, threads=True)
        if data.empty:
            return {}, ""
        close = data["Close"]

        # Correlation matrix (20-day window, core 6 assets only)
        try:
            core_tks = {k: v for k, v in tickers.items() if k != "Copper"}
            subset = close[list(core_tks.values())].tail(20)
            inv = {v: k for k, v in core_tks.items()}
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
                        "price": round(lat, 2), "change": round(lat - prev, 2),
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

    # v8.4: added 5y5y forward inflation + NFCI
    series = {
        "Fed Funds Rate":        "DFF",
        "2Y Treasury":           "DGS2",
        "10Y Treasury":          "DGS10",
        "Yield Curve (10Y-2Y)":  "T10Y2Y",
        "Breakeven Inflation":   "T10YIE",
        "5Y5Y Forward Inflation":"T5YIFR",
        "HY Credit Spread":      "BAMLH0A0HYM2",
        "NFCI":                  "NFCI",
    }
    results = {}
    try:
        fred  = Fred(api_key=FRED_API_KEY)
        start = YESTERDAY - datetime.timedelta(days=14)
        for name, sid in series.items():
            try:
                s = fred.get_series(sid, observation_start=start).dropna()
                if len(s) >= 2:
                    lat, prev = float(s.iloc[-1]), float(s.iloc[-2])
                    results[name] = {
                        "value": round(lat, 3), "prev": round(prev, 3),
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
    """Returns (market_data_string, hard_truths_dict)."""
    if not yfd and not frd:
        return "", {}

    hard_truths = {}
    lines = ["## 預載市場數據（API 直取，精確度高於搜尋）\n"]
    if corr_text:
        lines.append(corr_text + "\n")

    if yfd:
        lines.append("### 價格（yfinance，收盤價）")
        for n, d in yfd.items():
            if d["change"] is not None:
                dr = "↑" if d["change"] > 0 else "↓" if d["change"] < 0 else "→"
                lines.append(f"- {n}: {d['price']}（收盤價）({dr} {d['pct']:+.2f}%) [{d['date']}]")
                hard_truths[f"{n}_price"] = d["price"]
                hard_truths[f"{n}_pct"] = d["pct"]
                hard_truths[f"{n}_direction"] = (
                    "up" if d["change"] > 0 else "down" if d["change"] < 0 else "flat"
                )
            else:
                lines.append(f"- {n}: {d['price']}（收盤價）[{d['date']}]")
                hard_truths[f"{n}_price"] = d["price"]
        lines.append("")

        # v8.4: Copper/Gold ratio
        if "Copper" in yfd and "Gold" in yfd:
            cu = yfd["Copper"]["price"]
            au = yfd["Gold"]["price"]
            if au > 0:
                cu_au = round(cu / au * 1000, 3)  # *1000 for readability
                lines.append(f"### 衍生：Copper/Gold Ratio = {cu_au} (×1000)")
                lines.append("  高→景氣擴張預期；低→避險/衰退預期\n")
                hard_truths["copper_gold_ratio"] = cu_au

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
        fwd = frd.get("5Y5Y Forward Inflation", {})
        nfci = frd.get("NFCI", {})

        if yc.get("value") is not None:
            v = yc["value"]
            tag = "倒掛（衰退訊號）" if v < 0 else "平坦（謹慎）" if v < 0.5 else "正常"
            lines.append(f"- 殖利率曲線 (10Y-2Y)：{v}% — {tag}")
            hard_truths["yield_curve_value"] = v
            hard_truths["yield_curve_inverted"] = v < 0

        if n10.get("value") is not None and be.get("value") is not None:
            ry_today = round(n10["value"] - be["value"], 3)
            hard_truths["real_yield_value"] = ry_today
            ry_direction = "flat"
            if n10.get("prev") is not None and be.get("prev") is not None:
                ry_prev = round(n10["prev"] - be["prev"], 3)
                delta = ry_today - ry_prev
                ry_direction = "up" if delta > 0.001 else "down" if delta < -0.001 else "flat"
            hard_truths["real_yield_direction"] = ry_direction
            dr_label = {"up": "↑", "down": "↓", "flat": "→"}[ry_direction]
            lines.append(f"- 實質利率：{ry_today}% ({dr_label}) [= {n10['value']}% − BEI {be['value']}%]")

        if be.get("value") is not None:
            hard_truths["breakeven_value"] = be["value"]
        if hy.get("value") is not None:
            v = hy["value"]
            tag = "壓力" if v > 5.0 else "偏緊" if v < 3.5 else "正常"
            lines.append(f"- HY 信用利差：{v}% — {tag}")
            hard_truths["hy_spread_value"] = v

        # v8.4: 5y5y forward — cleaner than 10Y BEI for medium-term inflation
        if fwd.get("value") is not None:
            v = fwd["value"]
            lines.append(f"- 5Y5Y 遠期通膨預期：{v}%（比 10Y BEI 更少短期噪音）")
            hard_truths["forward_5y5y"] = v
            # Divergence signal
            if be.get("value") is not None:
                gap = round(be["value"] - v, 3)
                if abs(gap) > 0.15:
                    lines.append(f"  ⚡ BEI vs 5Y5Y 缺口：{gap:+.3f}%（>0.15 = 短期通膨噪音過高）")

        # v8.4: NFCI (weekly, lower freq)
        if nfci.get("value") is not None:
            v = nfci["value"]
            tag = "緊縮" if v > 0 else "寬鬆"
            lines.append(f"- NFCI 金融條件指數：{v} — {tag}（>0=緊縮，<0=寬鬆，週頻）")
            hard_truths["nfci_value"] = v
        lines.append("")

    lines.append(
        "（直接使用以上數據，不需搜尋驗證。方向與幅度以收盤價為準。"
        "若搜尋顯示盤中波動，可在敘事中補充，但數據切面以此為準。）\n"
    )
    return "\n".join(lines), hard_truths


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 0b — RELATIONAL GUARDRAIL (cross-asset consistency, deterministic)
# ══════════════════════════════════════════════════════════════════════════════

def run_relational_guardrail(hard_truths: dict) -> list[str]:
    """Python-based cross-asset consistency rules.
    Returns list of flags to inject into Analyst context.
    These are NOT errors — they are anomalies requiring explanation."""
    flags = []
    if not hard_truths:
        return flags

    gold_dir = hard_truths.get("Gold_direction")
    ry_dir   = hard_truths.get("real_yield_direction")
    spx_dir  = hard_truths.get("SPX_direction")
    dxy_dir  = hard_truths.get("DXY_direction")
    vix_pct  = hard_truths.get("VIX_pct", 0)
    spx_pct  = hard_truths.get("SPX_pct", 0)
    brent_pct = hard_truths.get("Brent_pct", 0)
    bei      = hard_truths.get("breakeven_value")
    fwd_5y5y = hard_truths.get("forward_5y5y")

    # Rule 1: Gold up + Real yield up → requires explanation
    if gold_dir == "up" and ry_dir == "up":
        flags.append(
            "⚡ RELATIONAL FLAG: Gold ↑ + 實質利率 ↑ — 歷史上負相關。"
            "需解釋：央行購金？地緣避險溢價？美元信用折價？"
        )

    # Rule 2: SPX up + VIX up (with threshold)
    if spx_pct > 0.5 and vix_pct > 3.0:
        flags.append(
            f"⚡ RELATIONAL FLAG: SPX +{spx_pct}% + VIX +{vix_pct}% — "
            "股指與恐慌指數同漲。短擠軋？選擇權 gamma squeeze？"
        )

    # Rule 3: Oil down big + BEI up → inflation expectation inconsistency
    if brent_pct < -5.0 and bei is not None and fwd_5y5y is not None:
        if hard_truths.get("breakeven_value", 0) > (fwd_5y5y or 0):
            flags.append(
                f"⚡ RELATIONAL FLAG: Brent {brent_pct:+.1f}% 但 BEI > 5Y5Y — "
                "油價崩但通膨預期未等比例下修，供應鏈黏性？"
            )

    # Rule 4: SPX up + Real yield up → likely short-covering, not fundamental
    if spx_dir == "up" and ry_dir == "up" and spx_pct > 0.5:
        flags.append(
            "⚡ RELATIONAL FLAG: SPX ↑ + 實質利率 ↑ — 估值邏輯矛盾。"
            "必須定調為倉位回補或流動性驅動，不可歸因於基本面改善。"
        )

    # Rule 5: Narrative vs price coherence — overall risk-on vs risk-off
    risk_on_count = sum([
        spx_dir == "up",
        gold_dir == "down",
        dxy_dir == "down",
        hard_truths.get("VIX_direction") == "down",
    ])
    risk_off_count = sum([
        spx_dir == "down",
        gold_dir == "up",
        dxy_dir == "up",
        hard_truths.get("VIX_direction") == "up",
    ])
    if risk_on_count >= 3:
        flags.append("📊 REGIME SIGNAL: 3+ risk-on indicators — 整體偏向風險偏好回歸")
    elif risk_off_count >= 3:
        flags.append("📊 REGIME SIGNAL: 3+ risk-off indicators — 整體偏向避險")
    elif risk_on_count >= 2 and risk_off_count >= 2:
        flags.append("📊 REGIME SIGNAL: 混合訊號 — 資產間缺乏共識，方向性押注風險高")

    return flags


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — DAILY SCORECARD (T+1 backtest)
# ══════════════════════════════════════════════════════════════════════════════

def run_daily_scorecard(yfd: dict) -> tuple[str, str]:
    """Compare yesterday's direction calls against today's actual prices.
    Returns (scorecard_line, feedback_text_for_analyst).
    scorecard_line is stored in L5. feedback_text is injected into today's Analyst."""
    yesterday_str = YESTERDAY.strftime("%Y-%m-%d")

    # 1. Read yesterday's report to extract direction calls
    try:
        data = notion_post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
            {"filter": {"and": [
                {"property": "Date",  "date":   {"equals": yesterday_str}},
                {"property": "Type",  "select": {"equals": "Daily"}},
            ]}}
        )
        results = data.get("results", [])
        if not results:
            return "", ""
        content = read_page_content(results[0]["id"])
    except Exception as e:
        print(f"    ⚠ Scorecard: cannot read yesterday's report ({e})")
        return "", ""

    # 2. Extract direction calls using Haiku (structured extraction)
    extract_prompt = f"""從以下報告的「配置羅盤」段落中，提取方向判斷。
只輸出純 JSON，無 markdown：
{{"calls": [{{"asset": "資產名", "direction": "up/down/neutral", "conviction": "H/M/L"}}]}}

只提取這5類：美股(SPX)、黃金(Gold)、美元(DXY)、美債長端(UST10Y)、原油(Brent)。
若找不到某資產，跳過。

報告內容（截取配置相關段落）：
---
{content[-2000:]}
---"""

    try:
        raw = call_claude(
            "只輸出純 JSON，無 markdown 標記。",
            extract_prompt, MODEL_HAIKU, max_tokens=300
        )
        raw = _repair_json(raw)
        calls_data = json.loads(raw)
        calls = calls_data.get("calls", [])
    except Exception as e:
        print(f"    ⚠ Scorecard: extraction failed ({e})")
        return "", ""

    if not calls:
        return "", ""

    # 3. Score against today's actuals
    asset_map = {
        "SPX": "SPX", "美股": "SPX",
        "Gold": "Gold", "黃金": "Gold",
        "DXY": "DXY", "美元": "DXY",
        "UST10Y": "UST10Y", "美債": "UST10Y",
        "Brent": "Brent", "原油": "Brent",
    }

    score_parts = []
    total_score = 0
    total_possible = 0
    conviction_weights = {"H": 3, "M": 2, "L": 1}

    for call in calls:
        asset_raw = call.get("asset", "")
        direction = call.get("direction", "").lower()
        conviction = call.get("conviction", "M").upper()
        weight = conviction_weights.get(conviction, 2)

        # Map to our ticker names
        asset = None
        for key, val in asset_map.items():
            if key.lower() in asset_raw.lower():
                asset = val
                break
        if not asset or asset not in yfd:
            continue

        actual_dir = "up" if yfd[asset].get("change", 0) and yfd[asset]["change"] > 0 else \
                     "down" if yfd[asset].get("change", 0) and yfd[asset]["change"] < 0 else "flat"
        actual_pct = yfd[asset].get("pct", 0) or 0

        # Score
        if direction == "neutral":
            hit = abs(actual_pct) < 0.5
            mark = "✓" if hit else "½"
            pts = weight if hit else weight * 0.5
        else:
            hit = (direction == actual_dir)
            mark = "✓" if hit else "✗"
            pts = weight if hit else -weight

        total_score += pts
        total_possible += weight
        actual_arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(actual_dir, "?")
        score_parts.append(f"{asset}:{direction}:{conviction}:{mark}(actual:{actual_arrow}{actual_pct:+.1f}%)")

    if not score_parts:
        return "", ""

    scorecard_line = f"{yesterday_str} | {' | '.join(score_parts)} | score:{total_score}/{total_possible}"

    # 4. Read existing scorecard for rolling stats
    try:
        old_scorecard = read_memo(SCORECARD_TITLE)
    except Exception:
        old_scorecard = ""

    all_lines = [ln.strip() for ln in old_scorecard.strip().split("\n") if ln.strip()] if old_scorecard else []
    all_lines.append(scorecard_line)

    # Keep last 30 days
    cutoff = (TODAY - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    all_lines = [ln for ln in all_lines if ln[:10] >= cutoff]

    # Calculate rolling hit rates
    hits_7d, total_7d = 0, 0
    hits_30d, total_30d = 0, 0
    cutoff_7d = (TODAY - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    for ln in all_lines:
        line_hits = ln.count(":✓")
        line_misses = ln.count(":✗")
        line_half = ln.count(":½")
        line_total = line_hits + line_misses + line_half
        hits_30d += line_hits + line_half * 0.5
        total_30d += line_total
        if ln[:10] >= cutoff_7d:
            hits_7d += line_hits + line_half * 0.5
            total_7d += line_total

    rate_7d = round(hits_7d / total_7d * 100, 1) if total_7d > 0 else 0
    rate_30d = round(hits_30d / total_30d * 100, 1) if total_30d > 0 else 0

    # Save updated scorecard
    try:
        safe_overwrite_memo(SCORECARD_TITLE, "\n".join(all_lines))
    except Exception as e:
        print(f"    ⚠ Scorecard save failed ({e})")

    # 5. Build feedback text for Analyst
    feedback = f"""### 預測回測（L5 Scorecard）
昨日方向性回測：{scorecard_line}
近 7 日 hit rate: {rate_7d}% | 近 30 日: {rate_30d}%"""

    # v8.4: Conviction dampener
    if rate_7d < 55 and total_7d >= 5:
        feedback += "\n⚠ 近 7 日 hit rate < 55%：今日 conviction 自動降一級（H→M, M→L）。反思哪類判斷最弱。"

    # Identify systematic weaknesses
    miss_assets = re.findall(r"(\w+):\w+:\w+:✗", scorecard_line)
    if miss_assets:
        feedback += f"\n昨日錯誤資產：{', '.join(miss_assets)}——分析錯因後調整今日同類判斷。"

    return "\n".join(all_lines), feedback


# ══════════════════════════════════════════════════════════════════════════════
# ANALYST + DEVIL'S ADVOCATE
# ══════════════════════════════════════════════════════════════════════════════

# v8.4: Added 6th attack (base_rate_neglect), feedback loop, relational flags
ANALYST_SYSTEM = f"""你是全球宏觀對沖基金的情報分析師兼首席風險官。
Prompt version: {PROMPT_VERSION}

重要：若收到預載市場數據（yfinance + FRED），直接使用，不需搜尋市場價格。3次 web_search 全部用於敘事性搜尋。

【絕對宏觀法則（Macro Physics Engine）】
1. 實質殖利率 = 名目殖利率 − 通膨預期（BEI）。Python 已預先計算，直接引用。
2. 實質殖利率上升 → 壓縮高估值資產估值倍數。
3. 若市場背離（實質利率升、美股卻漲），定調為倉位回補或流動性幻覺。
4. 5Y5Y 遠期通膨比 10Y BEI 更乾淨——當兩者分歧 >15bps，優先用 5Y5Y 判斷趨勢。
5. Copper/Gold ratio 上升 = 景氣擴張預期；下降 = 衰退預期。

【數據法則】
- 預載數據是收盤價，精確度最高。搜尋可能是盤中報價。
- 方向與幅度以預載為準。禁止四捨五入或記憶性改寫。

【Relational Flags】
若收到 ⚡ RELATIONAL FLAG，必須在草稿中明確回應該 flag：
解釋矛盾的原因，或承認不確定性。不可忽略。

【Scorecard Feedback】
若收到預測回測（L5），必須：
1. 承認昨日錯誤項目
2. 若 hit rate < 55%，所有 conviction 降一級
3. 分析錯誤模式（哪類資產最弱？哪種 regime 判斷最差？）

分析規則：
- 1-2 個 highest-impact 事件走完整 So What 鏈
- 每個核心判斷後執行六種結構化攻擊【攻擊結果】：
  1. regime_misclassification — 替代 regime 解讀
  2. timing_error — 方向正確但時機錯誤
  3. reflexivity_break — 倉位擁擠使 thesis 失效
  4. second_order_inversion — 因果鏈反轉條件
  5. omitted_variable_bias — 隱藏變數
  6. base_rate_neglect — 歷史上這類事件的基準機率是多少？你是否因敘事顯著性高估了概率？
  攻擊後若改變判斷，標注修正版本。

【歷史案例法則】
- 年份必須準確（紅海危機=2023-2024，俄烏=2022，SVB=2023.3）
- 每個案例附至少一個可驗證數據點

Thesis 規則：
- NEW_THESIS: {{"name":"...","statement":"...","assets":[...],"invalidators":[...],"measurable_outcome":"具體可驗證的結果","time_horizon":"1w/2w/1m"}}
- INVALIDATE_THESIS: {{"name":"..."}}

繁體中文，保留英文術語。直接輸出。3次 web_search。"""


def build_analyst_prompt(layer1: str, layer2: str, layer3: str,
                          layer4: str, knowledge_history: str,
                          market_data: str, relational_flags: list[str],
                          scorecard_feedback: str) -> str:
    ctx = ""
    if market_data:
        ctx += f"\n{market_data}\n"

    # v8.4: relational flags
    if relational_flags:
        ctx += "\n### 跨資產一致性警報（Relational Guardrail）\n"
        ctx += "\n".join(relational_flags) + "\n"

    # v8.4: scorecard feedback loop
    if scorecard_feedback:
        ctx += f"\n{scorecard_feedback}\n"

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

3次搜尋（依序）：
{searches}
{ctx}
草稿結構：

## 資產快照
Brent、10Y UST、DXY、SPX、Gold + Copper/Gold ratio + 5Y5Y forward
逐字使用預載數據數字。

## Relational Flags 回應
逐條回應收到的 ⚡ flags（若有）。

## 核心事件
1-2 個 highest-impact 事件 + So What 鏈 + 【攻擊結果】（六種）。

## 邊陲：{PERIPHERY_LABEL}

## Knowledge Desk 素材
1個概念，年份準確。

## 前瞻訊號
48-72hr，3-5 個 catalysts。

## 資產方向
含 conviction（若 L5 hit rate < 55% 則降一級）。

（thesis 變動標記於末尾。）"""


# ══════════════════════════════════════════════════════════════════════════════
# GUARDRAILS (unchanged from v8.3)
# ══════════════════════════════════════════════════════════════════════════════

def perform_logic_guardrail(text: str, hard_truths: dict, stage: str = "analyst") -> str:
    if not hard_truths:
        return ""
    checks = []
    for asset in ["SPX", "Brent", "Gold", "DXY", "UST10Y", "VIX"]:
        pk, pctk, dk = f"{asset}_price", f"{asset}_pct", f"{asset}_direction"
        if pk in hard_truths:
            checks.append(f"- {asset}: 收盤價={hard_truths[pk]}, 漲跌幅={hard_truths.get(pctk,'N/A')}%, 方向={hard_truths.get(dk,'N/A')}")
    if hard_truths.get("real_yield_value") is not None:
        checks.append(f"- 實質利率: {hard_truths['real_yield_value']}%, 方向={hard_truths.get('real_yield_direction','N/A')}")
    if hard_truths.get("yield_curve_inverted") is not None:
        checks.append(f"- 殖利率曲線: 倒掛={'是' if hard_truths['yield_curve_inverted'] else '否'}")
    if hard_truths.get("breakeven_value") is not None:
        checks.append(f"- BEI: {hard_truths['breakeven_value']}%")

    check_prompt = f"""嚴格數據審核。精確數據：
{chr(10).join(checks)}

待審核 {stage} 文本（前4000字）：
---
{text[:4000]}
---

檢查：資產方向、漲跌幅偏差>1.5%、價格偏差>2%、實質利率方向、殖利率曲線。
全部正確→PASS。有衝突→逐條列出。只輸出結論。"""

    try:
        result = call_claude("數據校驗。無誤→PASS，有誤→列出。", check_prompt, MODEL_HAIKU, max_tokens=400)
        if "PASS" in result.upper() and "不" not in result and "錯" not in result:
            return ""
        return f"\n\n【{stage}數據警告】：{result.strip()}\n修正此矛盾。"
    except Exception as e:
        print(f"    ⚠ Guardrail ({stage}): {e}"); return ""


LOGIC_REVIEWER_SYSTEM = """首席邏輯審查官。不搜尋，不寫作，只挑剔。

審查標準：
1. 因果跳躍
2. 結論超出數據
3. 時間框架混淆
4. 缺失反向論證
5. 循環論證
6. 歷史事實錯位（紅海=2023-2024, 俄烏=2022, SVB=2023.3, 日圓干預=2022.9/2024.4）
7. base_rate_neglect：核心預測的歷史基準機率是否被忽略？

PASS 或列出 2-4 個缺陷：[類型] 描述 → 修正建議"""

def perform_logic_review(analyst_draft: str) -> str:
    try:
        result = call_claude(LOGIC_REVIEWER_SYSTEM,
            f"審查邏輯鏈與歷史事實：\n---\n{analyst_draft}\n---\n無問題→PASS。",
            MODEL_OPUS, max_tokens=800)
        return "" if result.strip().upper().startswith("PASS") else result.strip()
    except Exception as e:
        print(f"    ⚠ Logic review: {e}"); return ""


# ══════════════════════════════════════════════════════════════════════════════
# NARRATOR
# ══════════════════════════════════════════════════════════════════════════════

NARRATOR_SYSTEM = f"""宏觀對沖基金出身、橫跨金融與國際政治的複合型分析師。
Prompt version: {PROMPT_VERSION}

三重身份：策略師（配置）、國際關係學者（權力結構）、知識領路人（概念定位）。
讀者：政治學學生，志在金融。目標：讀完後今天看世界的方式跟昨天不一樣。

【敘事紀律】禁止後設語彙（攻擊框架、替代解讀、修正後判斷）。批判性視角無縫呈現。
【數據法則】數據錨點中的數字必須逐字引用，不得修改。
【Relational Flags】若草稿回應了 ⚡ flags，在敘事中自然呈現其邏輯張力。
【Scorecard】若草稿包含昨日回測，在「今日張力」或「配置羅盤」中簡短提及。

conviction 嚴格格式：H (65-80%) / M (55-65%) / L (45-55%)
繁體中文，保留英文術語。🔴🟠🟡 以外禁止 emoji。直接輸出。"""


def build_narrator_prompt(analyst_draft: str, hard_truths: dict,
                           guardrail_warning: str = "", logic_review: str = "") -> str:
    # Data anchor
    anchor_lines = []
    if hard_truths:
        anchor_lines.append("!!! 數據錨點（不可修改）!!!")
        for asset in ["SPX", "Brent", "Gold", "DXY", "UST10Y", "VIX"]:
            p = hard_truths.get(f"{asset}_price")
            pct = hard_truths.get(f"{asset}_pct")
            d = hard_truths.get(f"{asset}_direction")
            if p is not None:
                arr = {"up":"↑","down":"↓","flat":"→"}.get(d,"?")
                anchor_lines.append(f"- {asset}: {p} ({arr} {pct:+.2f}%)" if pct else f"- {asset}: {p}")
        ry = hard_truths.get("real_yield_value")
        if ry is not None:
            anchor_lines.append(f"- 實質利率: {ry}% ({hard_truths.get('real_yield_direction','?')})")
        anchor_lines.append("數據切面所有數字必須與錨點一致。")

    correction = "\n".join(anchor_lines) if anchor_lines else ""
    if guardrail_warning:
        correction += f"\n\n!!! 數據修正 !!!\n{guardrail_warning}"
    if logic_review:
        correction += f"\n\n!!! 邏輯修正（Opus）!!!\n{logic_review}\n修正這些缺陷。"

    return f"""整合草稿，輸出最終報告。{correction}

=== 草稿 ===
{analyst_draft}

嚴格8段：

# Daily Intelligence Brief
{DATE_LABEL} | Strategy & Political Economy Desk

---

## 一、今日張力
一句核心矛盾。若有昨日回測，可嵌入。

---

## 二、數據切面
5條（Brent、10Y UST、DXY、SPX、Gold）+ 選擇性加入 Cu/Au ratio 或 5Y5Y：
- **指標（縮寫）** 數值 ↑/↓ — 意義
【所有數字與錨點一致】

---

## 三、今日主線
1000字內。教授風格。含 So What 鏈。自然融入攻擊。

---

## 四、權力地圖
### 得利方 / ### 受損方 / ### Risk Map（🔴🟠🟡+機率）/ ### 今日關鍵變數

---

## 五、邊陲訊號：{PERIPHERY_LABEL}
2段。無因果傳導則明確說「兩條平行線」。

---

## 六、配置羅盤
### 方向判斷（5條，含 conviction H/M/L）
### 前瞻監控（48-72hr，3-5 catalysts）

---

## 七、Knowledge Desk
### 概念：[名稱]
為什麼重要、實戰應用、歷史案例（年份準確）、當前問題

---

## 八、今日思考題

---
**資料來源**（1-3條）"""


# ══════════════════════════════════════════════════════════════════════════════
# LAYER UPDATE (enhanced L3 schema)
# ══════════════════════════════════════════════════════════════════════════════

LAYER_UPDATE_SYSTEM = """宏觀對沖基金資料管理員。輸出合法 JSON，不加說明或代碼塊。"""

def build_layer_update_prompt(report_summary: str, analyst_draft: str,
                               old_l2: str, old_l3: str, old_l4: str,
                               old_kh: str) -> str:
    thesis_signals = "\n".join(
        line.strip() for line in analyst_draft.split("\n")
        if "NEW_THESIS:" in line or "INVALIDATE_THESIS:" in line
    ) or "（今日無新 thesis）"

    return f"""更新記憶層。輸出純 JSON：
{{"layer2":"...", "layer3":[...], "layer4":[...], "knowledge_topic":"..."}}

今日（{DATE_STR}）：{report_summary[:600]}
Thesis 訊號：{thesis_signals}

現有 L2：{old_l2 or "（空）"}
現有 L3：{old_l3 or "[]"}
現有 L4：{old_l4 or "[]"}

L2 規則：末尾加今日條目，刪>7天：
{DATE_STR}
regime: [regime]
driver: [driver]
policy: [policy]
fragility: [fragility]

L3 規則（v8.4 增強）：
JSON陣列，格式：{{"name":"...","statement":"...","date":"...","assets":[...],"invalidators":[...],"measurable_outcome":"具體可驗證結果","time_horizon":"1w/2w/1m","status":"active","outcome":null,"outcome_date":null,"outcome_method":null}}
- 新增 NEW_THESIS（含 measurable_outcome + time_horizon）
- INVALIDATE_THESIS → status="invalidated"
- 刪除>30天 invalidated

L4 規則：
JSON陣列：{{"date":"...","attack_type":"...","description":"...","thesis_revised":true/false}}
attack_type 含新增 base_rate_neglect。加今日1條，刪>14天。"""


# ══════════════════════════════════════════════════════════════════════════════
# WEEKLY REVIEW (enhanced: thesis outcomes + prompt governance)
# ══════════════════════════════════════════════════════════════════════════════

WEEKLY_SYSTEM = f"""宏觀對沖基金資深策略師，負責週度總結。
Prompt version: {PROMPT_VERSION}
繁體中文，保留英文術語。禁止表格。"""

def build_weekly_prompt(layer2: str, layer3: str, scorecard: str) -> str:
    week_start = (TODAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    return f"""本週每日判斷：
{layer2 or "（無）"}

Thesis 清單：
{layer3 or "[]"}

本週預測回測（L5）：
{scorecard or "（無歷史數據）"}

# Weekly Intelligence Review
{week_start} ~ {DATE_STR} | Strategy & Political Economy Desk

## 本週核心主題
3-5 個主線，段落。

## 跨資產表現回顧

## 預測 vs 實際
回顧方向性判斷：哪些對、哪些錯、錯在哪裡。引用 L5 數據。

## Thesis 追蹤與判定
對每個 active thesis 評估本週進展：
- confirmed（方向正確，預期時間內）
- partially_confirmed（方向對但時間/幅度偏）
- wrong（方向錯或 invalidator 觸發）
- inconclusive（尚無明確結論）
輸出格式：THESIS_OUTCOME: {{"name":"...","outcome":"...","outcome_date":"{DATE_STR}","outcome_method":"analyst_judgment","notes":"..."}}

## 思考題追蹤

## 下週關鍵觀察點（5個）

## Prompt Governance Review
- 本週 hit rate 趨勢（引用 L5）
- 是否觀察到敘事慣性（重複相同框架）
- 是否有系統性偏差（哪類資產持續判錯）
- 建議 prompt 調整（若有）：描述修改 + 預期效果
- 若無需調整，寫 "PROMPT_STATUS: stable"

## 週度 Meta Insight
一段，150字內。

---
**資料來源**（5條）"""


# ══════════════════════════════════════════════════════════════════════════════
# MONTHLY META REVIEW (scaffolding — runs on 1st of month)
# ══════════════════════════════════════════════════════════════════════════════

MONTHLY_SYSTEM = f"""你是宏觀研究系統的首席品質官。
Prompt version: {PROMPT_VERSION}
任務：月度 meta-analysis。繁體中文。"""

def build_monthly_prompt(scorecard: str, layer3: str, knowledge_history: str) -> str:
    month_start = TODAY.replace(day=1) - datetime.timedelta(days=30)
    return f"""# Monthly Meta Review
{month_start.strftime('%Y-%m')} | System Quality Assessment

L5 Scorecard（近30天）：
{scorecard or "（無）"}

L3 Thesis 清單：
{layer3 or "[]"}

Knowledge History：
{knowledge_history or "（無）"}

請輸出：

## 1. 預測品質分析
- 方向性 hit rate 趨勢（逐週）
- 哪些資產預測最強 / 最弱
- H conviction 的 hit rate 是否 > 65%？若否，calibration 有系統偏差
- 最常見的錯誤模式

## 2. Thesis 生存率
- 總生成數 / active / confirmed / wrong / inconclusive / expired
- 平均 thesis 半衰期（從建立到 outcome 判定的天數）
- 哪類 thesis 存活率最高

## 3. 知識覆蓋分析
- Knowledge Desk 主題分佈（concept / mechanism / structural）
- 是否有盲區

## 4. Prompt 效能評估
- 本月 prompt 版本：{PROMPT_VERSION}
- 與上月比較：hit rate 變化、coherence 變化
- 哪些 prompt 機制有效（relational guardrail? base_rate_neglect?）
- 哪些需要調整

## 5. 下月建議
- prompt 調整建議（附理由和預期效果）
- 新增指標建議
- 系統架構建議

---
**PROMPT_CHANGE_PROPOSAL**（若有）：
{{"from":"{PROMPT_VERSION}","to":"...","changes":[{{"what":"...","why":"...","expected_impact":"..."}}]}}"""


# ══════════════════════════════════════════════════════════════════════════════
# CLAUDE API
# ══════════════════════════════════════════════════════════════════════════════

def call_claude_with_search(system: str, user: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": user}]
    search_count = 0
    text_blocks = []
    for _ in range(8):
        response = client.messages.create(
            model=MODEL_SONNET, max_tokens=5500,
            thinking={"type": "enabled", "budget_tokens": 2000},
            system=system,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        for block in response.content:
            if hasattr(block, "type") and block.type == "tool_use":
                search_count += 1
        if response.stop_reason == "end_turn" and search_count >= 3:
            return "\n".join(text_blocks)
        messages.append({"role": "assistant", "content": response.content})
        tool_results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": "Search executed."}
            for b in response.content if b.type == "tool_use"
        ]
        if not tool_results:
            if search_count < 3:
                print(f"    ⚠ Search ended early: {search_count}/3")
            return "\n".join(text_blocks)
        messages.append({"role": "user", "content": tool_results})
    return "\n".join(text_blocks)

def call_claude(system: str, user: str, model: str, max_tokens: int = 3000) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(model=model, max_tokens=max_tokens,
                                  system=system, messages=[{"role":"user","content":user}])
    return msg.content[0].text


# ══════════════════════════════════════════════════════════════════════════════
# MARKDOWN → NOTION
# ══════════════════════════════════════════════════════════════════════════════

def clean_md(md: str) -> str:
    lines = []
    for line in md.split("\n"):
        stripped = line.strip()
        if re.match(r"^[-*]?\s*[Ll]ist\s*$", stripped): continue
        if re.match(r"^[-*]\s*$", stripped): continue
        if line.startswith("* "): line = "- " + line[2:]
        lines.append(line.rstrip())
    return "\n".join(lines)

def parse_inline(text: str) -> list:
    rich = []
    for m in re.finditer(r"\*\*(.+?)\*\*|\*(.+?)\*|([^*]+)", text, re.DOTALL):
        bold_t, italic_t, plain_t = m.group(1), m.group(2), m.group(3)
        seg, ann = (bold_t, {"bold": True}) if bold_t else (italic_t, {"italic": True}) if italic_t else (plain_t, {})
        for i in range(0, max(1, len(seg)), 2000):
            chunk = seg[i:i+2000]
            if not chunk: continue
            rt = {"type": "text", "text": {"content": chunk}}
            if ann: rt["annotations"] = ann
            rich.append(rt)
    return rich or [{"type": "text", "text": {"content": ""}}]

def mk(btype: str, rich: list) -> dict:
    return {"object": "block", "type": btype, btype: {"rich_text": rich}}

def markdown_to_notion_blocks(md: str) -> list:
    md = clean_md(md)
    blocks = []
    for line in md.split("\n"):
        if line.startswith("# "): blocks.append(mk("heading_1", parse_inline(line[2:].strip())))
        elif line.startswith("## "): blocks.append(mk("heading_2", parse_inline(line[3:].strip())))
        elif line.startswith("### "): blocks.append(mk("heading_3", parse_inline(line[4:].strip())))
        elif re.match(r"^-{3,}$", line.strip()): blocks.append({"object":"block","type":"divider","divider":{}})
        elif line.startswith("- "):
            text = line[2:].strip()
            if text: blocks.append(mk("bulleted_list_item", parse_inline(text)))
        elif re.match(r"^\d+\.\s", line):
            text = re.sub(r"^\d+\.\s+", "", line).strip()
            if text: blocks.append(mk("numbered_list_item", parse_inline(text)))
        elif line.strip().startswith("|") and line.strip().endswith("|"):
            if re.match(r"^[\|\s\-:]+$", line.strip()): continue
            cells = [c.strip() for c in line.strip().strip("|").split("|") if c.strip()]
            if cells: blocks.append(mk("bulleted_list_item", parse_inline(" | ".join(cells))))
        elif line.strip(): blocks.append(mk("paragraph", parse_inline(line.strip())))
    return blocks


# ══════════════════════════════════════════════════════════════════════════════
# NOTION HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def notion_post(url, payload):
    resp = with_retry(httpx.post, url, headers=NOTION_HEADERS, json=payload, timeout=TIMEOUT)
    resp.raise_for_status(); return resp.json()
def notion_patch(url, payload):
    resp = with_retry(httpx.patch, url, headers=NOTION_HEADERS, json=payload, timeout=TIMEOUT)
    resp.raise_for_status(); return resp.json()
def notion_get(url):
    resp = with_retry(httpx.get, url, headers=NOTION_HEADERS, timeout=TIMEOUT)
    resp.raise_for_status(); return resp.json()
def notion_delete(url):
    with_retry(httpx.delete, url, headers=NOTION_HEADERS, timeout=TIMEOUT)

def read_page_content(page_id, page_size=200):
    data = notion_get(f"https://api.notion.com/v1/blocks/{page_id}/children?page_size={page_size}")
    return "\n".join("".join(t.get("plain_text","") for t in
        block.get(block.get("type",""),{}).get("rich_text",[]))
        for block in data.get("results",[])
        if "".join(t.get("plain_text","") for t in block.get(block.get("type",""),{}).get("rich_text",[])))

def append_blocks(page_id, content):
    blocks = markdown_to_notion_blocks(content)
    for i in range(0, len(blocks), 100):
        notion_patch(f"https://api.notion.com/v1/blocks/{page_id}/children", {"children": blocks[i:i+100]})

def create_page(db_id, title, report_type):
    data = notion_post("https://api.notion.com/v1/pages", {
        "parent": {"database_id": db_id},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": DATE_STR}},
            "Type": {"select": {"name": report_type.capitalize()}},
        },
    })
    return data["id"]

def get_or_create_daily_page(db_id, date_str):
    data = notion_post(f"https://api.notion.com/v1/databases/{db_id}/query",
        {"filter": {"and": [
            {"property": "Date", "date": {"equals": date_str}},
            {"property": "Type", "select": {"equals": "Daily"}},
        ]}})
    results = data.get("results", [])
    if results:
        page_id = results[0]["id"]
        print(f"    ↻ Existing page — updating ({page_id})")
        existing = notion_get(f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100")
        for block in existing.get("results", []):
            try: notion_delete(f"https://api.notion.com/v1/blocks/{block['id']}")
            except: pass
        return page_id
    return create_page(db_id, f"📊 Daily Brief | {date_str}", "daily")

def find_or_create_memo(title):
    data = notion_post(f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        {"filter": {"property": "Name", "title": {"equals": title}}})
    results = data.get("results", [])
    if results: return results[0]["id"]
    data = notion_post("https://api.notion.com/v1/pages", {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": DATE_STR}},
            "Type": {"select": {"name": "Memo"}},
        },
    })
    return data["id"]

def read_memo(title): return read_page_content(find_or_create_memo(title))

def safe_overwrite_memo(title, new_content):
    page_id = find_or_create_memo(title)
    data = notion_get(f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100")
    old_ids = [b["id"] for b in data.get("results", [])]
    append_blocks(page_id, new_content)
    for bid in old_ids:
        try: notion_delete(f"https://api.notion.com/v1/blocks/{bid}")
        except Exception as e: print(f"    ⚠ Delete block {bid}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MEMORY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def fetch_layer1():
    data = notion_post(f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        {"filter": {"and": [
            {"property": "Date", "date": {"equals": YESTERDAY.strftime("%Y-%m-%d")}},
            {"property": "Type", "select": {"equals": "Daily"}},
        ]}})
    results = data.get("results", [])
    if not results: return ""
    content = read_page_content(results[0]["id"])
    return content[:1000] + "…" if len(content) > 1000 else content

def _repair_json(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?\s*```$", "", raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*]", "]", raw)
    raw = re.sub(r"//[^\n]*\n", "\n", raw)
    return raw.strip()

def parse_layer_update(raw, old_l2, old_kh, report_summary):
    raw = _repair_json(raw)
    try:
        data = json.loads(raw)
        l2 = data.get("layer2", "")
        l3_raw, l4_raw = data.get("layer3", []), data.get("layer4", [])
        l3 = json.dumps(l3_raw, ensure_ascii=False, indent=2) if isinstance(l3_raw, list) else str(l3_raw)
        l4 = json.dumps(l4_raw, ensure_ascii=False, indent=2) if isinstance(l4_raw, list) else str(l4_raw)
        kt = data.get("knowledge_topic", "")
        if l2: return l2, l3, l4, kt
    except json.JSONDecodeError as e:
        print(f"    ⚠ JSON parse: {e}")
    print("    → Fallback L2 append")
    entry = f"{DATE_STR}：{report_summary[:100]}"
    if old_l2:
        cutoff = (TODAY - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        lines = old_l2.strip().split("\n")
        kept = [ln for ln in lines if not re.match(r"^\d{4}-\d{2}-\d{2}", ln) or ln[:10] >= cutoff]
        kept.append(entry)
        return "\n".join(kept), "", "", ""
    return entry, "", "", ""

def update_knowledge_history(old_kh, new_topic):
    if not new_topic: return old_kh
    entries = [ln.strip() for ln in old_kh.strip().split("\n") if ln.strip()] if old_kh else []
    entries.append(f"{DATE_STR}: {new_topic}")
    return "\n".join(entries[-10:])

def apply_thesis_outcomes(old_l3: str, weekly_text: str) -> str:
    """Parse THESIS_OUTCOME from weekly review and update L3."""
    outcomes = re.findall(r"THESIS_OUTCOME:\s*(\{.*?\})", weekly_text, re.DOTALL)
    if not outcomes or not old_l3:
        return old_l3
    try:
        theses = json.loads(old_l3) if old_l3.strip().startswith("[") else []
    except:
        return old_l3
    for raw_outcome in outcomes:
        try:
            oc = json.loads(_repair_json(raw_outcome))
            name = oc.get("name", "")
            for t in theses:
                if t.get("name") == name:
                    t["outcome"] = oc.get("outcome")
                    t["outcome_date"] = oc.get("outcome_date")
                    t["outcome_method"] = oc.get("outcome_method", "analyst_judgment")
                    if oc.get("outcome") in ("confirmed", "wrong"):
                        t["status"] = "resolved"
        except:
            continue
    return json.dumps(theses, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"[{DATE_STR}] Daily Intelligence Brief v8.4 — {PERIPHERY_LABEL}")
    print(f"  Prompt: {PROMPT_VERSION} | Sonnet: {MODEL_SONNET} | Opus: {MODEL_OPUS} | Haiku: {MODEL_HAIKU}")

    # ── 0. Market data ────────────────────────────────────────────────────────
    print("  → Layer 0: Market data...")
    yfd, corr_text = fetch_yfinance_data()
    frd = fetch_fred_data()
    market_data, hard_truths = format_market_data(yfd, frd, corr_text)
    if market_data:
        print(f"    ✓ yf:{len(yfd)} fred:{len(frd)} corr:{'✓' if corr_text else '∅'} truths:{len(hard_truths)}")
    else:
        print("    ⚠ APIs unavailable")

    # ── 0b. Relational guardrail ──────────────────────────────────────────────
    print("  → Layer 0b: Relational guardrail...")
    relational_flags = run_relational_guardrail(hard_truths)
    for f in relational_flags:
        print(f"    {f[:80]}...")
    if not relational_flags:
        print("    ✓ No cross-asset anomalies")

    # ── 0c. Daily Scorecard (T+1 backtest) ────────────────────────────────────
    print("  → Layer 4: Daily Scorecard (T+1)...")
    scorecard_feedback = ""
    try:
        scorecard_data, scorecard_feedback = run_daily_scorecard(yfd)
        if scorecard_feedback:
            print(f"    ✓ Scorecard computed")
        else:
            print("    ∅ No yesterday data or no calls extracted")
    except Exception as e:
        print(f"    ⚠ Scorecard failed ({e})")

    # ── 1. Load memory ────────────────────────────────────────────────────────
    print("  → Loading memory...")
    try:
        layer1 = fetch_layer1()
        layer2 = read_memo(LAYER2_TITLE)
        layer3 = read_memo(LAYER3_TITLE)
        layer4 = read_memo(LAYER4_TITLE)
        knowledge_history = read_memo(KNOWLEDGE_HISTORY)
        print(f"    L1={'✓' if layer1 else '∅'} L2={'✓' if layer2 else '∅'} "
              f"L3={'✓' if layer3 else '∅'} L4={'✓' if layer4 else '∅'} KH={'✓' if knowledge_history else '∅'}")
    except Exception as e:
        print(f"    ⚠ Memory load failed ({e})")
        layer1 = layer2 = layer3 = layer4 = knowledge_history = ""

    # ── 2. Analyst ────────────────────────────────────────────────────────────
    print("  → Layer 1: Analyst draft (Sonnet + 3 searches)...")
    analyst_draft = with_retry(
        call_claude_with_search, ANALYST_SYSTEM,
        build_analyst_prompt(layer1, layer2, layer3, layer4, knowledge_history,
                              market_data, relational_flags, scorecard_feedback),
    )
    print(f"  ✓ Draft ({len(analyst_draft)} chars)")

    # ── 2.5 Guardrails ───────────────────────────────────────────────────────
    print("  → Layer 1b: Data guardrail (Haiku)...")
    guardrail = perform_logic_guardrail(analyst_draft, hard_truths, "analyst")
    print("    ⚠ Issues found" if guardrail else "    ✓ Pass")

    print("  → Layer 1c: Logic review (Opus)...")
    logic_review = perform_logic_review(analyst_draft)
    if logic_review:
        print(f"    ⚠ {logic_review[:120]}...")
    else:
        print("    ✓ Pass")

    # ── 3. Narrator ──────────────────────────────────────────────────────────
    print("  → Layer 2: Narrator (Sonnet)...")
    final_report = with_retry(
        call_claude, NARRATOR_SYSTEM,
        build_narrator_prompt(analyst_draft, hard_truths, guardrail, logic_review),
        MODEL_SONNET, max_tokens=5500,
    )
    print(f"  ✓ Report ({len(final_report)} chars)")

    # ── 3.5 Post-narrator audit ──────────────────────────────────────────────
    print("  → Layer 2b: Post-narrator audit (Haiku)...")
    post_warning = perform_logic_guardrail(final_report, hard_truths, "narrator")
    if post_warning:
        print("    ⚠ Drift → patching...")
        try:
            final_report = with_retry(call_claude,
                "數據校對員。只修正數據錯誤，其他不改。輸出完整報告。",
                f"修正以下錯誤：{post_warning}\n\n=== 原報告 ===\n{final_report}",
                MODEL_SONNET, max_tokens=5500)
            print("    ✓ Patched")
        except Exception as e:
            print(f"    ⚠ Patch failed ({e})")
    else:
        print("    ✓ No drift")

    # ── 4. Push ──────────────────────────────────────────────────────────────
    print("  → Pushing to Notion...")
    page_id = get_or_create_daily_page(NOTION_DB_ID, DATE_STR)
    append_blocks(page_id, final_report)
    print(f"  ✓ Pushed ({page_id})")

    # ── 5. Memory update ─────────────────────────────────────────────────────
    print("  → Layer 3: Memory update (Haiku)...")
    try:
        update_raw = call_claude(LAYER_UPDATE_SYSTEM,
            build_layer_update_prompt(final_report[:1000], analyst_draft,
                                      layer2, layer3, layer4, knowledge_history),
            MODEL_HAIKU, max_tokens=1500)
        new_l2, new_l3, new_l4, new_kt = parse_layer_update(
            update_raw, layer2, knowledge_history, final_report[:1000])
        if new_l2: safe_overwrite_memo(LAYER2_TITLE, new_l2)
        if new_l3: safe_overwrite_memo(LAYER3_TITLE, new_l3)
        if new_l4: safe_overwrite_memo(LAYER4_TITLE, new_l4)
        updated_kh = update_knowledge_history(knowledge_history, new_kt)
        if updated_kh: safe_overwrite_memo(KNOWLEDGE_HISTORY, updated_kh)
        print(f"  ✓ Memory updated")
    except Exception as e:
        print(f"  ⚠ Memory failed ({e})")

    # ── 6. Weekly (Monday) ───────────────────────────────────────────────────
    if IS_MONDAY:
        print("  → Layer 5: Weekly review (Sonnet)...")
        try:
            fresh_l2 = read_memo(LAYER2_TITLE)
            fresh_l3 = read_memo(LAYER3_TITLE)
            scorecard_full = read_memo(SCORECARD_TITLE)
            weekly = with_retry(call_claude, WEEKLY_SYSTEM,
                build_weekly_prompt(fresh_l2, fresh_l3, scorecard_full),
                MODEL_SONNET, max_tokens=4000)
            week_start = (TODAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            w_id = create_page(NOTION_WEEKLY_DB,
                f"📅 Weekly Review | {week_start} ~ {DATE_STR}", "weekly")
            append_blocks(w_id, weekly)
            print(f"  ✓ Weekly pushed ({w_id})")

            # Apply thesis outcomes from weekly
            updated_l3 = apply_thesis_outcomes(fresh_l3, weekly)
            if updated_l3 != fresh_l3:
                safe_overwrite_memo(LAYER3_TITLE, updated_l3)
                print("  ✓ Thesis outcomes applied to L3")
        except Exception as e:
            print(f"  ⚠ Weekly failed ({e})")

    # ── 7. Monthly (1st of month) ────────────────────────────────────────────
    if IS_FIRST_OF_MONTH:
        print("  → Layer 6: Monthly meta review (Sonnet)...")
        try:
            scorecard_full = read_memo(SCORECARD_TITLE)
            fresh_l3 = read_memo(LAYER3_TITLE)
            kh = read_memo(KNOWLEDGE_HISTORY)
            monthly = with_retry(call_claude, MONTHLY_SYSTEM,
                build_monthly_prompt(scorecard_full, fresh_l3, kh),
                MODEL_SONNET, max_tokens=4000)
            m_id = create_page(NOTION_WEEKLY_DB,
                f"📈 Monthly Review | {TODAY.strftime('%Y-%m')}", "monthly")
            append_blocks(m_id, monthly)
            print(f"  ✓ Monthly pushed ({m_id})")

            # Log prompt version
            try:
                old_log = read_memo(PROMPT_LOG_TITLE)
                new_entry = f"{DATE_STR} | version: {PROMPT_VERSION} | monthly_review: {m_id}"
                safe_overwrite_memo(PROMPT_LOG_TITLE,
                    (old_log + "\n" + new_entry).strip())
            except:
                pass
        except Exception as e:
            print(f"  ⚠ Monthly failed ({e})")

    print("Done.")


if __name__ == "__main__":
    main()
