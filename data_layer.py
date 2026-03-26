"""
data_layer.py — Layer 0: 資料收集
所有可從 API 取得的數字，模型不得自行推論。
"""

import datetime as dt
import logging
import json

import pandas as pd
import numpy as np
import yfinance as yf
from fredapi import Fred
import requests
from bs4 import BeautifulSoup

from config import FRED_API_KEY, EIA_API_KEY, FRED_SERIES, YFINANCE_TICKERS

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# yfinance
# ─────────────────────────────────────────────────────────────────────

def fetch_yfinance(lookback_days: int = 5) -> dict:
    """取得所有 ticker 的最新價格、日漲跌幅、方向。"""
    result = {}
    end = dt.date.today()
    start = end - dt.timedelta(days=lookback_days + 5)  # 多抓幾天避免假日

    for name, ticker in YFINANCE_TICKERS.items():
        try:
            df = yf.download(ticker, start=str(start), end=str(end),
                             progress=False, auto_adjust=True)
            if df.empty or len(df) < 2:
                logger.warning(f"yfinance: {name} ({ticker}) 資料不足")
                continue

            # 處理 MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            latest = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2])
            pct = ((latest - prev) / prev) * 100

            direction = "up" if pct > 0.1 else ("down" if pct < -0.1 else "flat")

            result[f"{name}_price"] = round(latest, 2)
            result[f"{name}_pct"] = round(pct, 2)
            result[f"{name}_direction"] = direction
        except Exception as e:
            logger.error(f"yfinance error for {name}: {e}")

    # ── 衍生指標 ──
    copper_price = result.get("Copper_price")
    gold_price = result.get("Gold_price")
    if copper_price and gold_price and gold_price > 0:
        result["copper_gold_ratio"] = round(copper_price / gold_price, 4)

    vix9d = result.get("VIX9D_price")
    vix3m = result.get("VIX3M_price")
    if vix9d and vix3m and vix3m > 0:
        result["vix_term_ratio"] = round(vix9d / vix3m, 3)

    return result


# ─────────────────────────────────────────────────────────────────────
# FRED
# ─────────────────────────────────────────────────────────────────────

def fetch_fred() -> dict:
    """取得所有 FRED series 的最新值。"""
    fred = Fred(api_key=FRED_API_KEY)
    result = {}

    for name, series_id in FRED_SERIES.items():
        try:
            s = fred.get_series(series_id)
            s = s.dropna()
            if s.empty:
                logger.warning(f"FRED: {name} ({series_id}) 無資料")
                continue
            result[series_id] = round(float(s.iloc[-1]), 4)
        except Exception as e:
            logger.error(f"FRED error for {name} ({series_id}): {e}")

    return result


def compute_fred_derived(fred_data: dict) -> dict:
    """從 FRED 資料計算衍生指標。"""
    result = {}

    # Fed Funds Rate
    result["fed_funds_rate"] = fred_data.get("DFF")

    # Core PCE YoY
    result["core_pce_yoy"] = fred_data.get("PCEPILFE")

    # Unemployment Rate
    result["unemployment_rate"] = fred_data.get("UNRATE")

    # Yield Curve
    t10y2y = fred_data.get("T10Y2Y")
    result["yield_curve_value"] = t10y2y
    result["yield_curve_inverted"] = (t10y2y is not None and t10y2y < 0)

    # Breakeven Inflation
    bei = fred_data.get("T10YIE")

    # 5Y5Y Forward
    result["forward_5y5y"] = fred_data.get("T5YIFR")

    # NFCI
    result["nfci"] = fred_data.get("NFCI")

    # Real Yield = 10Y - BEI
    dgs10 = fred_data.get("DGS10")
    if dgs10 is not None and bei is not None:
        real_yield = round(dgs10 - bei, 4)
        result["real_yield_value"] = real_yield

    # Real Fed Funds = Fed Funds - Core PCE
    ff = fred_data.get("DFF")
    pce = fred_data.get("PCEPILFE")
    if ff is not None and pce is not None:
        result["real_fed_funds"] = round(ff - pce, 4)

    # Taylor Rule Deviation
    if ff is not None and pce is not None:
        # 簡化版 Taylor Rule: r* + 1.5*(inflation - 2) + 0.5*(output_gap)
        # 假設 r* = 2.5, output_gap ≈ 0 (用失業率近似)
        taylor = 2.5 + 1.5 * (pce - 2.0)
        if ff > taylor + 0.5:
            result["taylor_rule_deviation"] = "too_tight"
        elif ff < taylor - 0.5:
            result["taylor_rule_deviation"] = "too_loose"
        else:
            result["taylor_rule_deviation"] = "neutral"

    # HY-IG Spread
    hy = fred_data.get("BAMLH0A0HYM2")
    ig = fred_data.get("BAMLC0A0CM")
    if hy is not None and ig is not None:
        spread = round(hy - ig, 4)
        result["hy_ig_spread"] = spread
        result["credit_stress"] = spread > 3.5

    return result


# ─────────────────────────────────────────────────────────────────────
# 流動性三角 (Fed Balance Sheet - RRP - TGA)
# ─────────────────────────────────────────────────────────────────────

def fetch_liquidity(fred_data: dict) -> dict:
    """計算淨流動性 = Fed 資產 - RRP - TGA。"""
    result = {}

    walcl = fred_data.get("WALCL")  # Fed Balance Sheet (millions)
    rrp = fred_data.get("RRPONTSYD")  # RRP (billions)

    if walcl is None or rrp is None:
        return result

    # TGA from TreasuryDirect (fallback: 用固定估計)
    tga_bn = _fetch_tga()

    # WALCL 是 millions, RRP 是 billions
    walcl_bn = walcl / 1000.0
    rrp_bn = rrp  # 已經是 billions

    net_liq = round(walcl_bn - rrp_bn - tga_bn, 1)
    result["net_liquidity_bn"] = net_liq

    return result


def _fetch_tga() -> float:
    """從 Treasury API 取得 TGA 餘額 (billions)。"""
    try:
        url = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
               "/v1/accounting/dts/dts_table_1"
               "?sort=-record_date&page[size]=1"
               "&filter=account_type:eq:Treasury General Account (TGA) Closing Balance")
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("data"):
            val = float(data["data"][0]["close_today_bal"])
            return round(val / 1_000_000, 1)  # 轉成 billions (原始單位是 millions)
    except Exception as e:
        logger.warning(f"TGA fetch failed, using fallback: {e}")
    return 750.0  # fallback 估計值


# ─────────────────────────────────────────────────────────────────────
# CME FedWatch
# ─────────────────────────────────────────────────────────────────────

def fetch_fedwatch() -> dict:
    """抓取 CME FedWatch 降息機率。"""
    result = {}
    try:
        url = "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        # CME 的資料通常需要更複雜的抓取方式，這裡用 Grounding 替代
        # Analyst 會透過 Gemini Grounding 搜尋最新 FedWatch 資料
        result["fed_next_cut_prob"] = None  # 由 Analyst Grounding 補充
        result["fed_cuts_priced_in"] = None
    except Exception as e:
        logger.warning(f"FedWatch fetch failed: {e}")
    return result


# ─────────────────────────────────────────────────────────────────────
# EIA (原油庫存)
# ─────────────────────────────────────────────────────────────────────

def fetch_eia() -> dict:
    """EIA 週報原油庫存變化。"""
    result = {}
    if not EIA_API_KEY:
        logger.info("EIA_API_KEY not set, skipping")
        return result

    try:
        url = (f"https://api.eia.gov/v2/petroleum/sum/sndw/data/"
               f"?api_key={EIA_API_KEY}"
               f"&frequency=weekly&data[0]=value"
               f"&facets[product][]=EPC0"
               f"&facets[process][]=SAE"
               f"&sort[0][column]=period&sort[0][direction]=desc"
               f"&length=2")
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        records = data.get("response", {}).get("data", [])
        if len(records) >= 2:
            latest = float(records[0]["value"])
            prev = float(records[1]["value"])
            change = latest - prev
            result["crude_inventory_change"] = round(change, 1)
            if change < -3:
                result["crude_supply_signal"] = "tight"
            elif change > 3:
                result["crude_supply_signal"] = "oversupply"
            else:
                result["crude_supply_signal"] = "normal"
    except Exception as e:
        logger.error(f"EIA error: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────
# GDPNow (Atlanta Fed)
# ─────────────────────────────────────────────────────────────────────

def fetch_gdpnow() -> dict:
    """Atlanta Fed GDPNow 即時 GDP 估計。"""
    result = {}
    try:
        url = "https://www.atlantafed.org/-/media/documents/cqer/researchcq/gdpnow/GDPNowForecast.xlsx"
        # 修正重點：在這裡加上了 engine='openpyxl'
        df = pd.read_excel(url, sheet_name="Tracking", header=None, engine='openpyxl')
        
        # GDPNow 的 Excel 格式：最新預測值在特定位置
        # 嘗試找到最新的數字
        for i in range(len(df) - 1, -1, -1):
            for j in range(len(df.columns) - 1, -1, -1):
                val = df.iloc[i, j]
                if isinstance(val, (int, float)) and not np.isnan(val) and -10 < val < 20:
                    result["gdpnow_estimate"] = round(float(val), 2)
                    return result
    except Exception as e:
        logger.warning(f"GDPNow fetch failed: {e}")

    # Fallback: 用 FRED series (如果有)
    try:
        fred = Fred(api_key=FRED_API_KEY)
        s = fred.get_series("GDPNOW")
        if not s.empty:
            result["gdpnow_estimate"] = round(float(s.dropna().iloc[-1]), 2)
    except Exception:
        pass

    return result


# ─────────────────────────────────────────────────────────────────────
# NY Fed Recession Probability
# ─────────────────────────────────────────────────────────────────────

def fetch_recession_prob() -> dict:
    """NY Fed 12個月衰退機率。"""
    result = {}
    try:
        fred = Fred(api_key=FRED_API_KEY)
        s = fred.get_series("RECPROUSM156N")
        if not s.empty:
            result["recession_prob_12m"] = round(float(s.dropna().iloc[-1]), 2)
    except Exception as e:
        logger.warning(f"Recession prob fetch failed: {e}")
    return result


# ─────────────────────────────────────────────────────────────────────
# IMF SDMX (債務/GDP、財政餘額)
# ─────────────────────────────────────────────────────────────────────

def fetch_imf() -> dict:
    """IMF 資料：美國債務/GDP、財政餘額/GDP。"""
    result = {}
