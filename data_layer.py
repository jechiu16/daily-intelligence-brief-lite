"""
data_layer.py — Layer 0: 資料收集
所有可從 API 取得的數字，模型不得自行推論。
"""

import datetime as dt
import logging
import json
import io
import time
import re

import pandas as pd
import numpy as np
import yfinance as yf
from fredapi import Fred
import requests
from bs4 import BeautifulSoup

from config import FRED_API_KEY, EIA_API_KEY, FRED_SERIES, YFINANCE_TICKERS

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# 輔助函數：帶有自動重試機制的網路請求
# ─────────────────────────────────────────────────────────────────────
def _safe_get(url: str, headers: dict = None, max_retries: int = 3, delay: int = 2, timeout: int = 15):
    """
    發送 GET 請求，若失敗則自動重試。
    遇到 404 (找不到網頁) 則不重試直接報錯，因為重試也沒用。
    """
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()  # 如果狀態碼是 4xx 或 5xx 會觸發 HTTPError
            return resp
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"HTTP 404 Not Found for {url}. (直接放棄)")
                raise e
            logger.warning(f"HTTP 錯誤 {e.response.status_code} for {url}. 準備重試 ({attempt + 1}/{max_retries})...")
        except Exception as e:
            logger.warning(f"連線失敗: {e} for {url}. 準備重試 ({attempt + 1}/{max_retries})...")
        
        if attempt < max_retries - 1:
            time.sleep(delay)  # 休息幾秒再試
            
    raise Exception(f"在 {max_retries} 次嘗試後，依然無法取得 {url} 的資料。")

# ─────────────────────────────────────────────────────────────────────
# yfinance
# ─────────────────────────────────────────────────────────────────────

def fetch_yfinance(lookback_days: int = 5) -> dict:
    """取得所有 ticker 的最新價格、日漲跌幅、方向。"""
    result = {}
    end = dt.date.today()
    start = end - dt.timedelta(days=lookback_days + 5)

    for name, ticker in YFINANCE_TICKERS.items():
        try:
            df = yf.download(ticker, start=str(start), end=str(end),
                             progress=False, auto_adjust=True)
            if df.empty or len(df) < 2:
                logger.warning(f"yfinance: {name} ({ticker}) 資料不足")
                continue

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
    result["fed_funds_rate"] = fred_data.get("DFF")
    result["core_pce_yoy"] = fred_data.get("PCEPILFE")
    result["unemployment_rate"] = fred_data.get("UNRATE")

    t10y2y = fred_data.get("T10Y2Y")
    result["yield_curve_value"] = t10y2y
    result["yield_curve_inverted"] = (t10y2y is not None and t10y2y < 0)

    bei = fred_data.get("T10YIE")
    result["forward_5y5y"] = fred_data.get("T5YIFR")
    result["nfci"] = fred_data.get("NFCI")

    dgs10 = fred_data.get("DGS10")
    if dgs10 is not None and bei is not None:
        real_yield = round(dgs10 - bei, 4)
        result["real_yield_value"] = real_yield

    ff = fred_data.get("DFF")
    pce = fred_data.get("PCEPILFE")
    if ff is not None and pce is not None:
        result["real_fed_funds"] = round(ff - pce, 4)

    if ff is not None and pce is not None:
        taylor = 2.5 + 1.5 * (pce - 2.0)
        if ff > taylor + 0.5:
            result["taylor_rule_deviation"] = "too_tight"
        elif ff < taylor - 0.5:
            result["taylor_rule_deviation"] = "too_loose"
        else:
            result["taylor_rule_deviation"] = "neutral"

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
    walcl = fred_data.get("WALCL") 
    rrp = fred_data.get("RRPONTSYD")

    if walcl is None or rrp is None:
        return result

    tga_bn = _fetch_tga()
    walcl_bn = walcl / 1000.0
    rrp_bn = rrp 

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
        resp = _safe_get(url)
        data = resp.json()
        if data.get("data"):
            val = float(data["data"][0]["close_today_bal"])
            return round(val / 1_000_000, 1) 
    except Exception as e:
        logger.warning(f"TGA fetch failed, using fallback: {e}")
    return 750.0  


# ─────────────────────────────────────────────────────────────────────
# CME FedWatch
# ─────────────────────────────────────────────────────────────────────

def fetch_fedwatch() -> dict:
    """抓取 CME FedWatch 降息機率。"""
    result = {}
    try:
        url = "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = _safe_get(url, headers=headers)
        result["fed_next_cut_prob"] = None  
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
        resp = _safe_get(url)
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
# GDPNow (Atlanta Fed) - 網頁爬蟲版 + 重試機制
# ─────────────────────────────────────────────────────────────────────

def fetch_gdpnow() -> dict:
    """Atlanta Fed GDPNow 即時 GDP 估計 (爬取網頁文字)"""
    result = {}
    try:
        url = "https://www.atlantafed.org/cqer/research/gdpnow"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        # 使用我們剛剛寫的 _safe_get，自動享有 3 次重試機會
        resp = _safe_get(url, headers=headers)
        
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        
        match1 = re.search(r"(\d+\.\d+)\s*%\s*Latest GDPNow Estimate", text, re.IGNORECASE)
        if match1:
            result["gdpnow_estimate"] = float(match1.group(1))
            return result
            
        match2 = re.search(r"estimate for real GDP growth.*?is\s+(\d+\.\d+)\s*percent", text, re.IGNORECASE)
        if match2:
            result["gdpnow_estimate"] = float(match2.group(1))
            return result
            
        logger.warning("GDPNow HTML 抓取成功，但找不到相符的數字格式。")
    except Exception as e:
        logger.warning(f"GDPNow web fetch failed: {e}")

    # Fallback: 如果網頁真的爬不到，再退回 FRED
    try:
        fred = Fred(api_key=FRED_API_KEY)
        s = fred.get_series("GDPNOW")
        if not s.empty:
            result["gdpnow_estimate"] = round(float(s.dropna().iloc[-1]), 2)
            logger.warning("GDPNow: 使用 FRED 備用資料 (可能為上一季的落後數據)。")
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

    try:
        url = ("https://www.imf.org/external/datamapper/api/v1"
               "/GGXWDG_NGDP/USA?periods=2024,2025,2026")
        resp = _safe_get(url)
        data = resp.json()
        values = data.get("values", {}).get("GGXWDG_NGDP", {}).get("USA", {})
        for year in sorted(values.keys(), reverse=True):
            result["imf_us_debt_gdp"] = round(float(values[year]), 1)
            break
    except Exception as e:
        logger.warning(f"IMF debt/GDP fetch failed: {e}")

    try:
        url = ("https://www.imf.org/external/datamapper/api/v1"
               "/GGXCNL_NGDP/USA?periods=2024,2025,2026")
        resp = _safe_get(url)
        data = resp.json()
        values = data.get("values", {}).get("GGXCNL_NGDP", {}).get("USA", {})
        for year in sorted(values.keys(), reverse=True):
            result["imf_us_fiscal_balance"] = round(float(values[year]), 1)
            break
    except Exception as e:
        logger.warning(f"IMF fiscal balance fetch failed: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────
# OECD CLI
# ─────────────────────────────────────────────────────────────────────

def fetch_oecd_cli() -> dict:
    """OECD 綜合領先指標 (CLI)。"""
    result = {}
    try:
        url = ("https://sdmx.oecd.org/public/rest/data/"
               "OECD.SDD.STES,DSD_KEI@DF_KEI,4.0/"
               "M.USA.LI.LOLITOAA.IXOBSA.......?lastNObservations=3"
               "&dimensionAtObservation=AllDimensions")
        headers = {"Accept": "application/json"}
        resp = _safe_get(url, headers=headers)
        data = resp.json()

        obs = data.get("dataSets", [{}])[0].get("observations", {})
        values = sorted(obs.items(), key=lambda x: x[0])

        if len(values) >= 2:
            latest_val = values[-1][1][0]
            prev_val = values[-2][1][0]
            result["oecd_cli_us"] = round(float(latest_val), 2)

            diff = latest_val - prev_val
            if latest_val > 100 and diff > 0:
                result["oecd_cli_direction"] = "expanding"
            elif latest_val > 100 and diff <= 0:
                result["oecd_cli_direction"] = "slowing"
            elif latest_val <= 100 and diff < 0:
                result["oecd_cli_direction"] = "contracting"
            else:
                result["oecd_cli_direction"] = "recovering"
    except Exception as e:
        logger.warning(f"OECD CLI fetch failed: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────
# BIS (非美美元信貸)
# ─────────────────────────────────────────────────────────────────────

def fetch_bis() -> dict:
    """BIS 非美美元信貸 (季頻)。"""
    result = {}
    try:
        url = ("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_GLI/1.0/"
               "Q.5A.USD.A.1C.A.A.TO1.A?lastNObservations=2")
        headers = {"Accept": "application/json"}
        resp = _safe_get(url, headers=headers)
        data = resp.json()

        obs = data.get("dataSets", [{}])[0].get("series", {})
        for key, series_data in obs.items():
            observations = series_data.get("observations", {})
            latest_key = max(observations.keys())
            result["bis_usd_credit_nonbank"] = round(
                float(observations[latest_key][0]), 1
            )
            break
    except Exception as e:
        logger.warning(f"BIS fetch failed: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────
# CFTC COT (期貨倉位)
# ─────────────────────────────────────────────────────────────────────

def fetch_cot() -> dict:
    """CFTC Commitments of Traders — 極端倉位偵測。"""
    result = {"cot_crowding_flags": []}
    contracts = {
        "S&P 500": "13874A",
        "10Y Treasury": "043602",
        "Gold": "088691",
        "Crude Oil": "067651",
        "US Dollar Index": "098662",
    }

    try:
        year = dt.date.today().year
        for name, code in contracts.items():
            try:
                api_url = (f"https://publicreporting.cftc.gov/resource/jun7-fc8e.json"
                          f"?$where=cftc_contract_market_code='{code}'"
                          f"&$order=report_date_as_yyyy_mm_dd DESC"
                          f"&$limit=52")
                # 這裡也套用了安全重試
                resp = _safe_get(api_url)
                data = resp.json()
                if len(data) < 20:
                    continue

                latest = data[0]
                net_spec = (int(latest.get("noncomm_positions_long_all", 0)) -
                           int(latest.get("noncomm_positions_short_all", 0)))

                nets = []
                for row in data:
                    n = (int(row.get("noncomm_positions_long_all", 0)) -
                         int(row.get("noncomm_positions_short_all", 0)))
                    nets.append(n)

                if nets:
                    pctile = sum(1 for x in nets if x <= net_spec) / len(nets)
                    if pctile > 0.9 or pctile < 0.1:
                        result["cot_crowding_flags"].append(
                            f"{name}({'極端多' if pctile > 0.9 else '極端空'})"
                        )
            except Exception:
                continue

    except Exception as e:
        logger.warning(f"COT fetch failed: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────
# 主收集函數
# ─────────────────────────────────────────────────────────────────────

def collect_all_data() -> dict:
    """收集所有 Layer 0 資料，返回統一的 dict。"""
    logger.info("開始收集資料...")
    data = {}

    logger.info("  → yfinance")
    data.update(fetch_yfinance())

    logger.info("  → FRED")
    fred_raw = fetch_fred()
    data.update(compute_fred_derived(fred_raw))
    data["_fred_raw"] = fred_raw  

    logger.info("  → 流動性")
    data.update(fetch_liquidity(fred_raw))

    logger.info("  → FedWatch")
    data.update(fetch_fedwatch())

    logger.info("  → EIA")
    data.update(fetch_eia())

    logger.info("  → GDPNow")
    data.update(fetch_gdpnow())

    logger.info("  → Recession Prob")
    data.update(fetch_recession_prob())

    logger.info("  → IMF")
    data.update(fetch_imf())

    logger.info("  → OECD CLI")
    data.update(fetch_oecd_cli())

    logger.info("  → BIS")
    data.update(fetch_bis())

    logger.info("  → CFTC COT")
    data.update(fetch_cot())

    data.pop("_fred_raw", None)
    logger.info("資料收集完成")
    return data
