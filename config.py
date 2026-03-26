"""
config.py — 環境變數、常數、模型設定
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
EIA_API_KEY = os.environ.get("EIA_API_KEY", "")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")

# ── Gemini 模型（2026-03 可用名稱）────────────────────────────────────
MODEL_ANALYST = "gemini-2.5-pro"               # Analyst: 主推理 + thinking
MODEL_FLASH = "gemini-2.5-flash"               # Logic Guardrail + Layer Update
MODEL_NARRATOR = "gemini-2.5-flash-lite"       # Narrator: 白話轉譯

# ── FRED Series ──────────────────────────────────────────────────────
FRED_SERIES = {
    "Fed Funds Rate":          "DFF",
    "10Y Treasury":            "DGS10",
    "2Y Treasury":             "DGS2",
    "Yield Curve (10Y-2Y)":    "T10Y2Y",
    "Breakeven Inflation":     "T10YIE",
    "5Y5Y Forward Inflation":  "T5YIFR",
    "HY Credit Spread":        "BAMLH0A0HYM2",
    "IG Credit Spread":        "BAMLC0A0CM",
    "Core PCE":                "PCEPILFE",
    "Nonfarm Payrolls":        "PAYEMS",
    "Unemployment Rate":       "UNRATE",
    "NFCI":                    "NFCI",
    "Fed Balance Sheet":       "WALCL",
    "RRP":                     "RRPONTSYD",
}

# ── yfinance Tickers ─────────────────────────────────────────────────
YFINANCE_TICKERS = {
    "SPX":    "^GSPC",
    "Brent":  "BZ=F",
    "Gold":   "GC=F",
    "DXY":    "DX-Y.NYB",
    "UST10Y": "^TNX",
    "VIX":    "^VIX",
    "VIX9D":  "^VIX9D",
    "VIX3M":  "^VIX3M",
    "Copper": "HG=F",
}

# ── Notion 記憶層頁面名稱 ────────────────────────────────────────────
NOTION_PAGES = {
    "L2": "__WeeklyCompressed__",
    "L3": "__LongTermTracker__",
    "L4": "__DevilsAdvocateLog__",
    "KH": "__KnowledgeHistory__",
}

# ── Thesis 預算 ──────────────────────────────────────────────────────
THESIS_MAX_NEW_PER_DAY = 2
THESIS_MAX_ACTIVE = 5

# ── Narrator 設定 ────────────────────────────────────────────────────
NARRATOR_MAX_TOKENS = 4000
REPORT_MAX_CHARS = 1700  # 約 1700 中文字
