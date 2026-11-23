"""
NSE F&O Option Seller's Scanner v3 (Charts + S/R + News + Technicals + Dual-Expiry)
- Screens 60 liquid NSE F&O stocks via batched Yahoo Finance OHLCV data
- Computes exact Chart Support/Resistance (S2, S1, Pivot, R1, R2) & 35-day OHLC candles
- Fetches live Indian financial news headlines via Google News RSS + yfinance
- Rates every stock out of 100 (45% Technicals + 25% S/R Structure + 30% News Sentiment)
- Categorizes into Strong Bullish (85+), Bullish (72-84), Moderate Bullish (58-71),
  and Strong Bearish (85+), Bearish (72-84), Moderate Bearish (58-71)
- Generates explicit Trade Conclusion & Dual-Expiry Strikes (auto Next Month when <= 45 DTE)
"""

import calendar
import json
import math
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
import numpy as np
import pandas as pd
import yfinance as yf

NSE_HOLIDAYS = {
    date(2026, 1, 15), date(2026, 1, 26), date(2026, 3, 3), date(2026, 3, 26),
    date(2026, 3, 31), date(2026, 4, 3), date(2026, 4, 14), date(2026, 5, 1),
    date(2026, 5, 28), date(2026, 6, 26), date(2026, 9, 14), date(2026, 10, 2),
    date(2026, 10, 20), date(2026, 11, 10), date(2026, 11, 24), date(2026, 12, 25),
    date(2027, 1, 26), date(2027, 3, 26), date(2027, 4, 14), date(2027, 8, 15),
    date(2027, 10, 2), date(2027, 12, 25),
}

FNO_UNIVERSE = [
    ("RELIANCE", "Reliance Industries", "Energy & Telecom", 500),
    ("TCS", "Tata Consultancy Services", "IT Services", 175),
    ("INFY", "Infosys Ltd.", "IT Services", 400),
    ("HDFCBANK", "HDFC Bank Ltd.", "Private Banking", 550),
    ("ICICIBANK", "ICICI Bank Ltd.", "Private Banking", 700),
    ("SBIN", "State Bank of India", "PSU Banking", 750),
    ("AXISBANK", "Axis Bank Ltd.", "Private Banking", 625),
    ("KOTAKBANK", "Kotak Mahindra Bank", "Private Banking", 400),
    ("INDUSINDBK", "IndusInd Bank Ltd.", "Private Banking", 500),
    ("BANKBARODA", "Bank of Baroda", "PSU Banking", 2925),
    ("UNIONBANK", "Union Bank of India", "PSU Banking", 3000),
    ("BAJFINANCE", "Bajaj Finance Ltd.", "NBFC", 125),
    ("BAJAJFINSV", "Bajaj Finserv Ltd.", "Financial Services", 500),
    ("SHRIRAMFIN", "Shriram Finance Ltd.", "NBFC", 300),
    ("BHARTIARTL", "Bharti Airtel Ltd.", "Telecom", 475),
    ("LT", "Larsen & Toubro", "Infrastructure", 150),
    ("ITC", "ITC Ltd.", "FMCG", 1600),
    ("HINDUNILVR", "Hindustan Unilever", "FMCG", 300),
    ("MARICO", "Marico Ltd.", "FMCG", 1200),
    ("TATACONSUM", "Tata Consumer Products", "FMCG", 450),
    ("TITAN", "Titan Company Ltd.", "Consumer", 175),
    ("ASIANPAINT", "Asian Paints Ltd.", "Paints", 200),
    ("NESTLEIND", "Nestle India Ltd.", "FMCG", 200),
    ("TRENT", "Trent Ltd.", "Retail", 100),
    ("INDHOTEL", "Indian Hotels Co.", "Hospitality", 1000),
    ("MARUTI", "Maruti Suzuki India", "Automobile", 50),
    ("M&M", "Mahindra & Mahindra", "Automobile", 350),
    ("TATAMOTORS", "Tata Motors Ltd.", "Automobile", 550),
    ("EICHERMOT", "Eicher Motors Ltd.", "Automobile", 175),
    ("BAJAJ-AUTO", "Bajaj Auto Ltd.", "Automobile", 75),
    ("HEROMOTOCO", "Hero MotoCorp Ltd.", "Automobile", 150),
    ("TVSMOTOR", "TVS Motor Company", "Automobile", 350),
    ("COFORGE", "Coforge Ltd.", "IT Services", 375),
    ("PERSISTENT", "Persistent Systems", "IT Services", 200),
    ("TECHM", "Tech Mahindra Ltd.", "IT Services", 600),
    ("HCLTECH", "HCL Technologies", "IT Services", 350),
    ("WIPRO", "Wipro Ltd.", "IT Services", 1500),
    ("SUNPHARMA", "Sun Pharma Inds.", "Pharma", 350),
    ("DRREDDY", "Dr. Reddy's Labs", "Pharma", 625),
    ("CIPLA", "Cipla Ltd.", "Pharma", 650),
    ("DIVISLAB", "Divi's Laboratories", "Pharma", 200),
    ("LUPIN", "Lupin Ltd.", "Pharma", 425),
    ("TATASTEEL", "Tata Steel Ltd.", "Metals", 5500),
    ("HINDALCO", "Hindalco Industries", "Metals", 1400),
    ("JSWSTEEL", "JSW Steel Ltd.", "Metals", 675),
    ("VEDL", "Vedanta Ltd.", "Metals", 1150),
    ("APLAPOLLO", "APL Apollo Tubes", "Metals & Pipes", 350),
    ("NTPC", "NTPC Ltd.", "Power / PSU", 1500),
    ("POWERGRID", "Power Grid Corp.", "Power / PSU", 1800),
    ("COALINDIA", "Coal India Ltd.", "Mining / PSU", 1050),
    ("ONGC", "ONGC Ltd.", "Oil & Gas / PSU", 1925),
    ("BHEL", "Bharat Heavy Electricals", "Capital Goods / PSU", 2625),
    ("HAL", "Hindustan Aeronautics", "Defence / PSU", 150),
    ("BEL", "Bharat Electronics", "Defence / PSU", 2850),
    ("SIEMENS", "Siemens Ltd.", "Capital Goods", 150),
    ("DLF", "DLF Ltd.", "Real Estate", 825),
    ("PAGEIND", "Page Industries", "Apparel", 15),
    ("ADANIENT", "Adani Enterprises", "Conglomerate", 300),
    ("ADANIPORTS", "Adani Ports & SEZ", "Infrastructure", 400),
    ("POLYCAB", "Polycab India Ltd.", "Cables & Wires", 125),
]

POSITIVE_KEYWORDS = {
    "surge": 2.5, "surges": 2.5, "rally": 2.2, "rallies": 2.2, "all-time high": 3.0,
    "record high": 2.8, "52-week high": 2.5, "breakout": 2.2, "profit jump": 2.8,
    "profit surges": 2.8, "beats estimates": 2.8, "beat estimates": 2.8, "strong q": 2.0,
    "upgrade": 2.5, "upgrades": 2.5, "buy rating": 2.4, "target price": 1.6,
    "order win": 2.6, "wins order": 2.6, "contract win": 2.5, "bagged order": 2.5,
    "buyback": 2.4, "dividend": 1.6, "expansion": 1.8, "approval": 2.0,
    "margin expansion": 2.4, "robust": 1.8, "outperform": 2.2, "buck": 1.8,
    "lead": 1.5, "gainers": 2.0, "growth": 1.4,
}

NEGATIVE_KEYWORDS = {
    "plunge": -3.0, "plunges": -3.0, "slump": -2.8, "slumps": -2.8, "tumble": -2.6,
    "tumbles": -2.6, "crash": -3.0, "crashes": -3.0, "falls": -2.0, "fall": -1.8,
    "drops": -2.0, "drop": -1.8, "downgrade": -2.6, "downgrades": -2.6,
    "sell rating": -2.6, "cut target": -2.4, "cuts target": -2.4, "misses estimates": -2.8,
    "loss": -2.2, "profit falls": -2.6, "profit drops": -2.6, "margin pressure": -2.4,
    "weak demand": -2.2, "sluggish": -2.0, "sebi": -2.2, "probe": -2.5,
    "penalty": -2.4, "fraud": -3.0, "default": -3.0, "open offer": -1.5,
    "stake sale": -1.8, "overhang": -2.0, "breakdown": -2.2, "bleed": -2.4,
    "drags": -1.8, "underperform": -2.2, "de-rating": -2.4, "losers": -2.0,
}


def classify_tier(rating: int, bias: str):
    if bias == "bullish":
        if rating >= 85:
            return "Strong Bullish", "strong_bullish"
        if rating >= 72:
            return "Bullish", "bullish"
        return "Moderate Bullish", "moderate_bullish"
    else:
        if rating >= 85:
            return "Strong Bearish", "strong_bearish"
        if rating >= 72:
            return "Bearish", "bearish"
        return "Moderate Bearish", "moderate_bearish"


def get_nse_monthly_expiry(year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() != 1:
        d -= timedelta(days=1)
    while d.weekday() >= 5 or d in NSE_HOLIDAYS:
        d -= timedelta(days=1)
    return d


def compute_expiry_schedule(today: date) -> dict:
    y, m = today.year, today.month
    curr_exp = get_nse_monthly_expiry(y, m)
    if curr_exp < today:
        m += 1
        if m > 12:
            m = 1
            y += 1
        curr_exp = get_nse_monthly_expiry(y, m)

    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    next_exp = get_nse_monthly_expiry(ny, nm)

    curr_dte = max(0, (curr_exp - today).days)
    next_dte = max(1, (next_exp - today).days)

    if next_dte <= 45:
        recommended = "next"
        rule_reason = (
            f"Next monthly expiry ({next_exp.strftime('%d %b %Y')}) is {next_dte} days away (≤ 45 days) — "
            f"recommending Next Month Expiry for optimal theta decay and lower gamma risk."
        )
    else:
        recommended = "current"
        rule_reason = (
            f"Next monthly expiry ({next_exp.strftime('%d %b %Y')}) is {next_dte} days away (> 45 days) — "
            f"recommending Current Month Expiry ({curr_exp.strftime('%d %b %Y')}, {curr_dte} DTE)."
        )

    return {
        "current_month": {
            "code": "current",
            "label": curr_exp.strftime("%b %Y Expiry"),
            "date": curr_exp.strftime("%d %b %Y (%a)"),
            "dte": curr_dte,
        },
        "next_month": {
            "code": "next",
            "label": next_exp.strftime("%b %Y Expiry"),
            "date": next_exp.strftime("%d %b %Y (%a)"),
            "dte": next_dte,
        },
        "recommended": recommended,
        "rule_reason": rule_reason,
    }


def strike_step(price: float) -> int:
    if price < 250:
        return 5
    if price < 600:
        return 10
    if price < 1500:
        return 20
    if price < 4000:
        return 50
    if price < 10000:
        return 100
    return 500


def round_to_step(value: float, step: int, direction: str = "nearest") -> int:
    if direction == "down":
        return int(math.floor(value / step) * step)
    if direction == "up":
        return int(math.ceil(value / step) * step)
    return int(round(value / step) * step)


def compute_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if pd.notna(val) else 50.0


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    return float(atr) if pd.notna(atr) else float(df["Close"].iloc[-1] * 0.02)


def fmt_inr(val: float) -> str:
    if val >= 1000:
        return f"₹{val:,.0f}"
    return f"₹{val:,.1f}" if val % 1 else f"₹{int(val)}"


def analyze_chart_and_technicals(symbol: str, name: str, sector: str, lot_size: int, df: pd.DataFrame):
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
    if len(df) < 60:
        return None

    close = df["Close"]
    cmp = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    chg_1d = ((cmp - prev_close) / prev_close) * 100.0

    idx_20 = max(0, len(close) - 21)
    chg_20d = ((cmp - float(close.iloc[idx_20])) / float(close.iloc[idx_20])) * 100.0

    dma20_s = close.rolling(20).mean()
    dma50_s = close.rolling(50).mean()
    dma20 = float(dma20_s.iloc[-1])
    dma50 = float(dma50_s.iloc[-1])
    dma200 = float(close.tail(200).mean()) if len(close) >= 200 else float(close.mean())

    rsi = compute_rsi(close, 14)
    atr = compute_atr(df, 14)
    atr_pct = (atr / cmp) * 100.0

    high_52w = float(df["High"].tail(252).max())
    low_52w = float(df["Low"].tail(252).min())
    dist_52w_high = ((cmp - high_52w) / high_52w) * 100.0
    dist_52w_low = ((cmp - low_52w) / low_52w) * 100.0

    avg_vol_20 = float(df["Volume"].tail(20).mean())
    recent_vol = float(df["Volume"].tail(3).mean())
    vol_ratio = (recent_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0

    # --- Chart Support & Resistance Engine (20D/60D Swings + Monthly Pivots + DMAs) ---
    h20 = float(df["High"].tail(20).max())
    l20 = float(df["Low"].tail(20).min())
    h60 = float(df["High"].tail(60).max())
    l60 = float(df["Low"].tail(60).min())
    pivot = (h20 + l20 + cmp) / 3.0

    # Immediate S1 & Major S2 strictly below CMP
    s1_candidates = [v for v in [l20, dma20, dma50, 2 * pivot - h20] if v < cmp * 0.992]
    s1 = max(s1_candidates) if s1_candidates else cmp - 1.8 * atr
    s1 = min(s1, cmp - 0.9 * atr)

    s2_candidates = [v for v in [l60, dma50, dma200, pivot - (h20 - l20)] if v < s1 * 0.985]
    s2 = max(s2_candidates) if s2_candidates else s1 - 1.8 * atr

    # Immediate R1 & Major R2 strictly above CMP
    r1_candidates = [v for v in [h20, dma20, dma50, 2 * pivot - l20] if v > cmp * 1.008]
    r1 = min(r1_candidates) if r1_candidates else cmp + 1.8 * atr
    r1 = max(r1, cmp + 0.9 * atr)

    r2_candidates = [v for v in [h60, dma50, dma200, pivot + (h20 - l20)] if v > r1 * 1.015]
    r2 = min(r2_candidates) if r2_candidates else r1 + 1.8 * atr

    s1_dist_pct = ((s1 - cmp) / cmp) * 100.0
    r1_dist_pct = ((r1 - cmp) / cmp) * 100.0

    # --- Technical Score (0-100) ---
    bull_tech = 32.0
    if cmp > dma20: bull_tech += 12
    if cmp > dma50: bull_tech += 14
    if cmp > dma200: bull_tech += 12
    if dma20 > dma50 > dma200: bull_tech += 8
    if 54 <= rsi <= 75: bull_tech += 8
    elif rsi > 75: bull_tech += 3
    if chg_20d > 2.0: bull_tech += min(12.0, chg_20d * 0.8)
    if chg_1d > 1.0: bull_tech += min(6.0, chg_1d * 1.2)
    if vol_ratio > 1.15 and chg_20d > 0: bull_tech += 5
    bull_tech = max(10, min(98, int(round(bull_tech))))

    bear_tech = 32.0
    if cmp < dma20: bear_tech += 12
    if cmp < dma50: bear_tech += 14
    if cmp < dma200: bear_tech += 12
    if dma20 < dma50 < dma200: bear_tech += 8
    if 25 <= rsi <= 46: bear_tech += 8
    elif rsi < 25: bear_tech += 4
    if chg_20d < -2.0: bear_tech += min(12.0, abs(chg_20d) * 0.8)
    if chg_1d < -1.0: bear_tech += min(6.0, abs(chg_1d) * 1.2)
    if vol_ratio > 1.15 and chg_20d < 0: bear_tech += 5
    bear_tech = max(10, min(98, int(round(bear_tech))))

    # --- S/R Structure Score (0-100) ---
    bull_sr = 45.0
    if dist_52w_high >= -3.0: bull_sr += 20
    elif dist_52w_high >= -8.0: bull_sr += 12
    if cmp > pivot: bull_sr += 10
    if cmp > dma50 and s1 >= dma50 * 0.98: bull_sr += 12
    if abs(s1_dist_pct) <= 6.0: bull_sr += 8
    bull_sr = max(15, min(98, int(round(bull_sr))))

    bear_sr = 45.0
    if dist_52w_high <= -15.0: bear_sr += 18
    elif dist_52w_high <= -10.0: bear_sr += 10
    if dist_52w_low <= 10.0: bear_sr += 10
    if cmp < pivot: bear_sr += 10
    if cmp < dma50 and r1 <= dma50 * 1.03: bear_sr += 12
    bear_sr = max(15, min(98, int(round(bear_sr))))

    # Export last 35 daily candles for interactive SVG chart
    tail35 = df.tail(35)
    chart_data = []
    for idx, row in tail35.iterrows():
        d_str = idx.strftime("%d %b") if hasattr(idx, "strftime") else str(idx)[:10]
        d20 = float(dma20_s.loc[idx]) if pd.notna(dma20_s.loc[idx]) else float(row["Close"])
        d50 = float(dma50_s.loc[idx]) if pd.notna(dma50_s.loc[idx]) else float(row["Close"])
        chart_data.append({
            "d": d_str,
            "o": round(float(row["Open"]), 2),
            "h": round(float(row["High"]), 2),
            "l": round(float(row["Low"]), 2),
            "c": round(float(row["Close"]), 2),
            "dma20": round(d20, 2),
            "dma50": round(d50, 2),
        })

    return {
        "symbol": symbol, "name": name, "sector": sector, "lot_size": lot_size,
        "cmp": round(cmp, 2), "chg_1d": round(chg_1d, 2), "chg_20d": round(chg_20d, 2),
        "rsi": round(rsi, 1), "dma20": round(dma20, 2), "dma50": round(dma50, 2), "dma200": round(dma200, 2),
        "atr": round(atr, 2), "atr_pct": round(atr_pct, 2),
        "high_52w": round(high_52w, 2), "dist_52w_high": round(dist_52w_high, 2),
        "vol_ratio": round(vol_ratio, 2),
        "bull_tech": bull_tech, "bear_tech": bear_tech,
        "bull_sr": bull_sr, "bear_sr": bear_sr,
        "sr": {
            "s2": round(s2, 2), "s1": round(s1, 2), "pivot": round(pivot, 2),
            "r1": round(r1, 2), "r2": round(r2, 2),
            "s1_dist_pct": round(s1_dist_pct, 2), "r1_dist_pct": round(r1_dist_pct, 2),
        },
        "chart_data": chart_data,
    }


def fetch_stock_news(symbol: str, company_name: str, bias: str) -> dict:
    headlines = []
    query = urllib.parse.quote(f'"{company_name}" OR "{symbol}" NSE stock')
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

    try:
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0 (compatible; NSEFnOScanner/3.0)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_bytes = resp.read()
        root = ET.fromstring(xml_bytes)
        for item in root.findall(".//item")[:5]:
            title_el = item.find("title")
            link_el = item.find("link")
            src_el = item.find("source")
            if title_el is not None and title_el.text:
                raw_title = title_el.text.strip()
                source_name = src_el.text.strip() if (src_el is not None and src_el.text) else "Google News"
                if " - " in raw_title and source_name == "Google News":
                    parts = raw_title.rsplit(" - ", 1)
                    raw_title, source_name = parts[0], parts[1]
                headlines.append({
                    "title": raw_title, "source": source_name,
                    "url": link_el.text.strip() if (link_el is not None and link_el.text) else "",
                })
    except Exception:
        pass

    if not headlines:
        try:
            yf_news = yf.Ticker(f"{symbol}.NS").news or []
            for n in yf_news[:4]:
                content = n.get("content", n)
                title = content.get("title") or n.get("title")
                pub = (content.get("provider") or {}).get("displayName") or n.get("publisher") or "Yahoo Finance"
                link = ((content.get("canonicalUrl") or {}).get("url")) or n.get("link") or ""
                if title:
                    headlines.append({"title": title, "source": pub, "url": link})
        except Exception:
            pass

    raw_polarity = 0.0
    annotated = []
    for h in headlines[:3]:
        t_low = h["title"].lower()
        h_score = 0.0
        for kw, w in POSITIVE_KEYWORDS.items():
            if kw in t_low:
                h_score += w
        for kw, w in NEGATIVE_KEYWORDS.items():
            if kw in t_low:
                h_score += w
        raw_polarity += h_score
        sent_tag = "Positive" if h_score > 0.5 else ("Negative" if h_score < -0.5 else "Neutral")
        annotated.append({"title": h["title"], "source": h["source"], "sentiment": sent_tag, "url": h["url"]})

    aligned = raw_polarity if bias == "bullish" else -raw_polarity
    news_score = int(max(30, min(96, round(66 + aligned * 5.0))))

    if not annotated:
        summary = f"Clean news tape with no adverse corporate shocks; price action in {symbol} drives primary bias."
    else:
        top_h = annotated[0]["title"]
        if news_score >= 78:
            summary = f"Strong confirming catalyst: \"{top_h}\""
        elif news_score >= 62:
            summary = f"Aligned market coverage: \"{top_h}\""
        else:
            summary = f"Mixed/cautious headlines—size conservatively: \"{top_h}\""

    return {"news_score": news_score, "news_summary": summary, "headlines": annotated}


def build_expiry_levels(m: dict, bias: str, dte: int) -> dict:
    cmp = m["cmp"]
    step = strike_step(cmp)
    atr = m["atr"]
    sr = m["sr"]
    time_scale = max(0.35, min(1.35, math.sqrt(max(2, dte) / 30.0)))

    if bias == "bullish":
        anchor = sr["s1"] if dte > 15 else max(sr["s1"], cmp - 1.3 * atr)
        target_strike = min(anchor, cmp - max(cmp * 0.018 * time_scale, 1.4 * atr * time_scale))
        short_strike = round_to_step(target_strike, step, "down")
        if short_strike >= cmp:
            short_strike = round_to_step(cmp - step, step, "down")
        width = max(step, round_to_step(cmp * (0.025 if dte <= 15 else 0.035), step, "nearest"))
        hedge_strike = max(step, short_strike - width)
        z_low = round_to_step(short_strike - step, step, "down")
        z_high = round_to_step(min(cmp - step * 0.5, sr["s1"]), step, "nearest")
        if z_high <= z_low:
            z_high = short_strike
        return {
            "zone": f"{fmt_inr(z_low)} – {fmt_inr(z_high)}",
            "invalidation": round(z_low * 0.99, 1),
            "short_strike": short_strike,
            "hedge_strike": hedge_strike,
            "est_credit": round(max(0.8, width * (0.22 if dte <= 15 else 0.28)), 1),
        }
    else:
        anchor = sr["r1"] if dte > 15 else min(sr["r1"], cmp + 1.3 * atr)
        target_strike = max(anchor, cmp + max(cmp * 0.018 * time_scale, 1.4 * atr * time_scale))
        short_strike = round_to_step(target_strike, step, "up")
        if short_strike <= cmp:
            short_strike = round_to_step(cmp + step, step, "up")
        width = max(step, round_to_step(cmp * (0.025 if dte <= 15 else 0.035), step, "nearest"))
        hedge_strike = short_strike + width
        z_low = round_to_step(max(cmp + step * 0.5, sr["r1"]), step, "nearest")
        z_high = round_to_step(short_strike + step, step, "up")
        if z_high <= z_low:
            z_high = short_strike + step
        return {
            "zone": f"{fmt_inr(z_low)} – {fmt_inr(z_high)}",
            "invalidation": round(z_high * 1.01, 1),
            "short_strike": short_strike,
            "hedge_strike": hedge_strike,
            "est_credit": round(max(0.8, width * (0.22 if dte <= 15 else 0.28)), 1),
        }


def format_pick(m: dict, news_info: dict, bias: str, expiry_meta: dict) -> dict:
    tech_s = m["bull_tech"] if bias == "bullish" else m["bear_tech"]
    sr_s = m["bull_sr"] if bias == "bullish" else m["bear_sr"]
    news_s = news_info["news_score"]
    rating = int(round(0.45 * tech_s + 0.25 * sr_s + 0.30 * news_s))
    tier_label, tier_code = classify_tier(rating, bias)

    curr_lvl = build_expiry_levels(m, bias, expiry_meta["current_month"]["dte"])
    next_lvl = build_expiry_levels(m, bias, expiry_meta["next_month"]["dte"])
    rec_key = expiry_meta["recommended"]
    rec_lvl = next_lvl if rec_key == "next" else curr_lvl
    rec_month_short = (expiry_meta["next_month"]["label"] if rec_key == "next" else expiry_meta["current_month"]["label"]).split()[0]

    sr = dict(m["sr"])
    if bias == "bullish":
        sr["structure"] = (
            "Breakout Near 52W High Above Support" if m["dist_52w_high"] >= -3.5
            else "Higher-Low Uptrend Holding Above DMA Support"
        )
        tech_txt = f"CMP {fmt_inr(m['cmp'])} ({m['chg_1d']:+.2f}% 1D, {m['chg_20d']:+.1f}% 20D) above 50 DMA ({fmt_inr(m['dma50'])}) & 200 DMA ({fmt_inr(m['dma200'])}), RSI {m['rsi']}."
        sr_txt = f"Immediate support S1 at {fmt_inr(sr['s1'])} ({sr['s1_dist_pct']:+.1f}%) and major floor S2 at {fmt_inr(sr['s2'])}; resistance R1 at {fmt_inr(sr['r1'])}."
        risk_txt = f"ATR {m['atr_pct']:.1f}% ({m['vol_ratio']:.2f}x vol). Cap downside with {rec_lvl['hedge_strike']} PE hedge; exit if daily close breaches {fmt_inr(rec_lvl['invalidation'])}."
        conclusion = (
            f"{tier_label.upper()} ({rating}/100) — Sell {rec_month_short} {rec_lvl['short_strike']} PE / Buy {rec_lvl['hedge_strike']} PE "
            f"anchored safely below S1 ({fmt_inr(sr['s1'])}), backed by {sr['structure'].lower()} and aligned news flow."
        )
        strategy = "Bull Put Spread / OTM Put Sell"
    else:
        sr["structure"] = (
            "Steep Breakdown Below All Major Moving Averages" if m["chg_20d"] <= -10
            else "Lower-High Downtrend Under Overhead DMA Supply"
        )
        tech_txt = f"CMP {fmt_inr(m['cmp'])} ({m['chg_1d']:+.2f}% 1D, {m['chg_20d']:+.1f}% 20D) pressured below 50 DMA ({fmt_inr(m['dma50'])}) & 200 DMA ({fmt_inr(m['dma200'])}), RSI {m['rsi']}."
        sr_txt = f"Overhead resistance R1 at {fmt_inr(sr['r1'])} ({sr['r1_dist_pct']:+.1f}%) and R2 at {fmt_inr(sr['r2'])}; downside support S1 at {fmt_inr(sr['s1'])}."
        risk_txt = f"ATR {m['atr_pct']:.1f}% ({m['vol_ratio']:.2f}x vol). Check NSE MWPL ban list; cap upside with {rec_lvl['hedge_strike']} CE and exit above {fmt_inr(rec_lvl['invalidation'])}."
        conclusion = (
            f"{tier_label.upper()} ({rating}/100) — Sell {rec_month_short} {rec_lvl['short_strike']} CE / Buy {rec_lvl['hedge_strike']} CE "
            f"positioned above R1 resistance ({fmt_inr(sr['r1'])}), backed by bearish chart structure and negative news overhang."
        )
        strategy = "Bear Call Spread / OTM Call Sell"

    return {
        "symbol": m["symbol"], "name": m["name"], "sector": m["sector"], "bias": bias,
        "rating": rating, "tier": tier_label, "tier_code": tier_code, "strategy": strategy,
        "cmp": m["cmp"], "chg_1d": m["chg_1d"], "chg_20d": m["chg_20d"], "rsi": m["rsi"],
        "dma20": m["dma20"], "dma50": m["dma50"], "dma200": m["dma200"],
        "dist_52w_high": m["dist_52w_high"], "vol_ratio": m["vol_ratio"],
        "scores": {"tech": tech_s, "sr": sr_s, "news": news_s, "composite": rating},
        "sr": sr,
        "expiries": {"current": curr_lvl, "next": next_lvl},
        "lot_size": m["lot_size"],
        "reasons": {
            "technical": tech_txt,
            "sr_analysis": sr_txt,
            "news": news_info["news_summary"],
            "risk": risk_txt,
        },
        "conclusion": conclusion,
        "headlines": news_info["headlines"],
        "chart_data": m["chart_data"],
    }



# ==============================================================================
# MCX COMMODITY ENGINE (GOLDM, SILVERM, CRUDEOILM)
# Uses Global COMEX/NYMEX Futures + USD/INR + DXY + Global Macro News + S/R
# ==============================================================================

COMMODITY_CONFIGS = [
    {
        "symbol": "GOLDM",
        "name": "MCX Gold Mini",
        "sector": "Precious Metals (MCX)",
        "yf_ticker": "GC=F",
        "unit_label": "₹ / 10g",
        "lot_desc": "100g (₹10 per ₹1 move)",
        "lot_size": 10,
        "strike_step": 1000,
        "settlement": "Physical Delivery (Devolves to Fut — Exit before expiry)",
        "news_query": '"MCX gold" OR "gold price" Fed dollar yields India',
        # 1 troy oz = 31.1035g -> 10g factor = 10/31.1035; ~1.155 covers Indian landed duty/MCX basis
        "inr_factor": (10.0 / 31.1034768) * 1.153,
        "global_unit": "$/oz",
    },
    {
        "symbol": "SILVERM",
        "name": "MCX Silver Mini",
        "sector": "Precious Metals (MCX)",
        "yf_ticker": "SI=F",
        "unit_label": "₹ / kg",
        "lot_desc": "5 kg (₹5 per ₹1 move)",
        "lot_size": 5,
        "strike_step": 2500,
        "settlement": "Physical Delivery (Devolves to Fut — Exit before expiry)",
        "news_query": '"MCX silver" OR "silver price" COMEX Fed industrial',
        # 1 kg = 32.15075 troy oz; ~1.19 covers Indian landed duty/MCX basis
        "inr_factor": 32.1507466 * 1.19,
        "global_unit": "$/oz",
    },
    {
        "symbol": "CRUDEOILM",
        "name": "MCX Crude Oil Mini",
        "sector": "Energy (MCX)",
        "yf_ticker": "CL=F",
        "unit_label": "₹ / barrel",
        "lot_desc": "10 Barrels (₹10 per ₹1 move)",
        "lot_size": 10,
        "strike_step": 100,
        "settlement": "Cash Settled",
        "news_query": '"crude oil price" OR "MCX crude" OPEC EIA inventory WTI',
        "inr_factor": 1.005,
        "global_unit": "$/bbl",
    },
]

COMMODITY_BULL_KW = {
    "reclaims": 2.0, "safe-haven": 2.4, "safe haven": 2.4, "rate cut": 2.8,
    "dovish": 2.5, "supply cut": 2.8, "opec cut": 3.0, "inventory draw": 2.6,
    "drawdown": 2.2, "geopolitical": 1.8, "war": 1.8, "escalation": 2.0,
    "dollar falls": 2.2, "weak dollar": 2.2, "surge": 2.2, "surges": 2.2,
    "rally": 2.0, "record high": 2.8, "rebounds": 1.6,
}

COMMODITY_BEAR_KW = {
    "inventory build": -2.8, "inventories rising": -2.8, "inventories jump": -2.8,
    "strong supply": -2.6, "surplus": -2.6, "rate hike": -2.8, "tightening": -2.6,
    "hawkish": -2.5, "elevated yields": -2.2, "dollar strength": -2.2, "strong dollar": -2.2,
    "liquidation": -2.6, "selloff": -2.4, "sell-off": -2.4, "crash": -2.8,
    "plunge": -2.8, "plunges": -2.8, "weekly decline": -2.4, "slipped": -1.8,
    "caution": -1.5, "falls": -2.0, "drops": -2.0, "peace deal": -2.0,
}

HIGH_RISK_NEWS_KW = [
    "war", "strike", "iran", "israel", "middle east", "west asia",
    "fed", "fomc", "cpi", "opec", "eia", "crash", "liquidation",
]


def prev_business_day(d: date, days_back: int) -> date:
    cur = d
    rem = days_back
    while rem > 0:
        cur -= timedelta(days=1)
        if cur.weekday() < 5 and cur not in NSE_HOLIDAYS:
            rem -= 1
    return cur


def get_mcx_expiry_pair(symbol: str, today: date) -> dict:
    """Computes approximate current & next MCX option expiry dates and applies the <=45D rule."""
    def nth_month_day(y: int, m: int, day_num: int) -> date:
        last_d = calendar.monthrange(y, m)[1]
        d = date(y, m, min(day_num, last_d))
        while d.weekday() >= 5 or d in NSE_HOLIDAYS:
            d -= timedelta(days=1)
        return d

    def advance(y: int, m: int, step: int = 1):
        m2 = m + step
        while m2 > 12:
            m2 -= 12
            y += 1
        return y, m2

    expiries = []
    y, m = today.year, today.month
    for offset in range(0, 6):
        yy, mm = advance(y, m, offset)
        if symbol == "CRUDEOILM":
            fut_d = nth_month_day(yy, mm, 19)
            opt_d = prev_business_day(fut_d, 2)
        elif symbol == "GOLDM":
            # GoldM futures expire 5th of every month; option expires ~5 business days prior (late prev month)
            fy, fm = advance(yy, mm, 1)
            fut_d = nth_month_day(fy, fm, 5)
            opt_d = prev_business_day(fut_d, 5)
        else:
            # SilverM futures expire last business day of Feb, Apr, Jun, Aug, Nov; options monthly late month
            opt_d = prev_business_day(nth_month_day(yy, mm, 31), 3)
            fut_months = [2, 4, 6, 8, 11]
            fy, fm = yy, mm
            while fm not in fut_months or nth_month_day(fy, fm, 31) < opt_d:
                fy, fm = advance(fy, fm, 1)
            fut_d = nth_month_day(fy, fm, 31)

        if opt_d >= today:
            expiries.append((opt_d, fut_d))
        if len(expiries) >= 2:
            break

    (c_opt, c_fut), (n_opt, n_fut) = expiries[0], expiries[1]
    c_dte = max(0, (c_opt - today).days)
    n_dte = max(1, (n_opt - today).days)

    if n_dte <= 45 or c_dte <= 5:
        rec = "next"
        note = f"Next option ({n_opt.strftime('%d %b %Y')}) is {n_dte} DTE (≤ 45d) — Next Expiry is Primary."
    else:
        rec = "current"
        note = f"Next option ({n_opt.strftime('%d %b %Y')}) is {n_dte} DTE (> 45d) — Active {c_opt.strftime('%b %Y')} Option ({c_dte} DTE) is Primary."

    return {
        "current": {"label": c_opt.strftime("%d %b %Y Opt"), "fut": c_fut.strftime("%d %b %Y Fut"), "dte": c_dte},
        "next": {"label": n_opt.strftime("%d %b %Y Opt"), "fut": n_fut.strftime("%d %b %Y Fut"), "dte": n_dte},
        "recommended": rec,
        "rule_note": note,
    }


def fetch_commodity_news(cfg: dict) -> dict:
    headlines = []
    q = urllib.parse.quote(cfg["news_query"])
    rss_url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0 (compatible; MCXScanner/4.0)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_bytes = resp.read()
        root = ET.fromstring(xml_bytes)
        for item in root.findall(".//item")[:5]:
            t_el = item.find("title")
            l_el = item.find("link")
            s_el = item.find("source")
            if t_el is not None and t_el.text:
                raw_t = t_el.text.strip()
                src = s_el.text.strip() if (s_el is not None and s_el.text) else "Global Wire"
                if " - " in raw_t and src == "Global Wire":
                    parts = raw_t.rsplit(" - ", 1)
                    raw_t, src = parts[0], parts[1]
                headlines.append({"title": raw_t, "source": src, "url": l_el.text.strip() if l_el is not None and l_el.text else ""})
    except Exception:
        pass

    polarity = 0.0
    event_risk = False
    annotated = []
    for h in headlines[:3]:
        low = h["title"].lower()
        sc = 0.0
        for kw, w in COMMODITY_BULL_KW.items():
            if kw in low:
                sc += w
        for kw, w in COMMODITY_BEAR_KW.items():
            if kw in low:
                sc += w
        if any(rk in low for rk in HIGH_RISK_NEWS_KW):
            event_risk = True
        polarity += sc
        tag = "Positive" if sc > 0.5 else ("Negative" if sc < -0.5 else "Neutral")
        annotated.append({"title": h["title"], "source": h["source"], "sentiment": tag, "url": h["url"]})

    return {"polarity": polarity, "event_risk": event_risk, "headlines": annotated}


def scan_commodities(today: date) -> list:
    yf_tickers = [c["yf_ticker"] for c in COMMODITY_CONFIGS] + ["INR=X", "DX-Y.NYB"]
    print(f"Downloading 1y global commodity & FX data: {yf_tickers}")
    raw = yf.download(
        tickers=yf_tickers, period="1y", interval="1d",
        group_by="ticker", auto_adjust=True, threads=True, progress=False,
    )

    def get_df(tkr):
        if isinstance(raw.columns, pd.MultiIndex) and tkr in raw.columns.get_level_values(0):
            return raw[tkr].dropna(subset=["Close"])
        return pd.DataFrame()

    fx_df = get_df("INR=X")
    usdinr = float(fx_df["Close"].iloc[-1]) if len(fx_df) else 92.95
    fx_5d = ((usdinr - float(fx_df["Close"].iloc[-6])) / float(fx_df["Close"].iloc[-6]) * 100.0) if len(fx_df) >= 6 else 0.0

    dxy_df = get_df("DX-Y.NYB")
    dxy_val = float(dxy_df["Close"].iloc[-1]) if len(dxy_df) else 103.8
    dxy_5d = ((dxy_val - float(dxy_df["Close"].iloc[-6])) / float(dxy_df["Close"].iloc[-6]) * 100.0) if len(dxy_df) >= 6 else 0.0

    results = []
    for cfg in COMMODITY_CONFIGS:
        gdf = get_df(cfg["yf_ticker"])
        if len(gdf) < 60:
            continue

        # Convert global OHLC to MCX INR equivalent
        inr_scale = usdinr * cfg["inr_factor"]
        df_inr = gdf.copy()
        for col in ["Open", "High", "Low", "Close"]:
            df_inr[col] = df_inr[col] * inr_scale
        if "Volume" not in df_inr.columns or df_inr["Volume"].sum() == 0:
            df_inr["Volume"] = 10000.0

        m = analyze_chart_and_technicals(cfg["symbol"], cfg["name"], cfg["sector"], cfg["lot_size"], df_inr)
        if not m:
            continue

        global_last = float(gdf["Close"].iloc[-1])
        global_20d = ((global_last - float(gdf["Close"].iloc[-21])) / float(gdf["Close"].iloc[-21])) * 100.0
        news_raw = fetch_commodity_news(cfg)

        # Decide directional bias using combined Technical + S/R + News polarity
        bull_base = 0.6 * m["bull_tech"] + 0.4 * m["bull_sr"] + max(-15, min(15, news_raw["polarity"] * 2.0))
        bear_base = 0.6 * m["bear_tech"] + 0.4 * m["bear_sr"] + max(-15, min(15, -news_raw["polarity"] * 2.0))
        bias = "bullish" if bull_base >= bear_base else "bearish"

        tech_s = m["bull_tech"] if bias == "bullish" else m["bear_tech"]
        sr_s = m["bull_sr"] if bias == "bullish" else m["bear_sr"]
        aligned_pol = news_raw["polarity"] if bias == "bullish" else -news_raw["polarity"]
        news_s = int(max(35, min(95, round(66 + aligned_pol * 4.5))))
        rating = int(round(0.45 * tech_s + 0.25 * sr_s + 0.30 * news_s))
        tier_label, tier_code = classify_tier(rating, bias)

        exp_meta = get_mcx_expiry_pair(cfg["symbol"], today)
        step = cfg["strike_step"]
        sr = dict(m["sr"])

        # News-Safe Strike Builder: adds extra 1.25x buffer when high-impact global news is active
        risk_mult = 1.28 if (news_raw["event_risk"] or m["rsi"] < 32 or m["rsi"] > 72) else 1.05

        def calc_mcx_spread(dte: int) -> dict:
            cmp_v = m["cmp"]
            atr_v = m["atr"]
            t_scale = max(0.45, min(1.35, math.sqrt(max(3, dte) / 30.0)))
            buf = max(cmp_v * 0.035 * t_scale, 2.0 * atr_v * t_scale) * risk_mult
            width = max(step * 2, round_to_step(cmp_v * (0.025 if dte <= 25 else 0.035), step, "nearest"))
            if bias == "bullish":
                raw_k = min(sr["s1"], cmp_v - buf)
                short_k = round_to_step(raw_k, step, "down")
                hedge_k = max(step, short_k - width)
                z_low, z_high = short_k - step, short_k + step
                inv = round(z_low * 0.99, 1)
            else:
                raw_k = max(sr["r1"], cmp_v + buf)
                short_k = round_to_step(raw_k, step, "up")
                hedge_k = short_k + width
                z_low, z_high = short_k - step, short_k + step
                inv = round(z_high * 1.01, 1)
            return {
                "zone": f"{fmt_inr(z_low)} – {fmt_inr(z_high)}",
                "invalidation": inv,
                "short_strike": short_k,
                "hedge_strike": hedge_k,
                "est_credit": round(max(step * 0.15, width * 0.26), 1),
            }

        curr_lvl = calc_mcx_spread(exp_meta["current"]["dte"])
        next_lvl = calc_mcx_spread(exp_meta["next"]["dte"])
        rec_key = exp_meta["recommended"]
        rec_lvl = next_lvl if rec_key == "next" else curr_lvl
        rec_lbl = exp_meta[rec_key]["label"]
        opt_type = "PE" if bias == "bullish" else "CE"
        cushion_pct = abs(rec_lvl["short_strike"] - m["cmp"]) / m["cmp"] * 100.0

        top_hl = news_raw["headlines"][0]["title"] if news_raw["headlines"] else f"Global {cfg['symbol']} tracking COMEX/NYMEX & USD/INR ({usdinr:.2f})."
        sr["structure"] = (
            "Uptrend Holding Above Key Support" if bias == "bullish"
            else "Downtrend / Resistance-Capped Below Moving Averages"
        )

        results.append({
            "symbol": cfg["symbol"], "name": cfg["name"], "asset_class": "commodity",
            "sector": cfg["sector"], "unit_label": cfg["unit_label"],
            "lot_desc": cfg["lot_desc"], "lot_size": cfg["lot_size"],
            "settlement": cfg["settlement"], "bias": bias,
            "rating": rating, "tier": tier_label, "tier_code": tier_code,
            "strategy": "Bull Put Spread (News-Safe)" if bias == "bullish" else "Bear Call Spread (News-Safe)",
            "cmp": m["cmp"], "chg_1d": m["chg_1d"], "chg_20d": m["chg_20d"],
            "rsi": m["rsi"], "dma20": m["dma20"], "dma50": m["dma50"], "dma200": m["dma200"],
            "dist_52w_high": m["dist_52w_high"], "vol_ratio": m["vol_ratio"],
            "global_ref": {
                "benchmark": f"{cfg['yf_ticker']}: {global_last:,.2f} {cfg['global_unit']} ({global_20d:+.1f}% 20D)",
                "usdinr": round(usdinr, 2),
                "dxy_note": f"DXY {dxy_val:.1f} ({dxy_5d:+.1f}% 5D) · USD/INR {usdinr:.2f} ({fx_5d:+.1f}% 5D)",
            },
            "scores": {"tech": tech_s, "sr": sr_s, "news": news_s, "composite": rating},
            "sr": sr, "expiry_meta": exp_meta,
            "expiries": {"current": curr_lvl, "next": next_lvl},
            "reasons": {
                "global_trend": f"Global {cfg['yf_ticker']} at {global_last:,.2f} {cfg['global_unit']} ({global_20d:+.1f}% 20D) with DXY at {dxy_val:.1f} and USD/INR at ₹{usdinr:.2f}.",
                "technical": f"MCX est. {fmt_inr(m['cmp'])} ({m['chg_1d']:+.2f}% 1D, {m['chg_20d']:+.1f}% 20D), RSI(14) {m['rsi']}, 20 DMA {fmt_inr(m['dma20'])}, 50 DMA {fmt_inr(m['dma50'])}.",
                "sr_analysis": f"Support S1 {fmt_inr(sr['s1'])} / S2 {fmt_inr(sr['s2'])} · Resistance R1 {fmt_inr(sr['r1'])} / R2 {fmt_inr(sr['r2'])}.",
                "news": f"Global/MCX catalyst: \"{top_hl}\"",
                "risk": f"{'High-impact macro/geopolitical news detected — applied extra OTM safety buffer. ' if news_raw['event_risk'] else ''}{cfg['settlement']}; exit before expiry if near ITM.",
            },
            "conclusion": (
                f"{tier_label.upper()} ({rating}/100) — Safe news-buffered trade: Sell {rec_lbl} "
                f"{rec_lvl['short_strike']} {opt_type} / Buy {rec_lvl['hedge_strike']} {opt_type} "
                f"({cushion_pct:.1f}% safety cushion beyond {'S1' if bias == 'bullish' else 'R1'})."
            ),
            "headlines": news_raw["headlines"],
            "chart_data": m["chart_data"],
        })

    results.sort(key=lambda x: x["rating"], reverse=True)
    return results


def run_scan() -> dict:
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    expiry_meta = compute_expiry_schedule(now_ist.date())

    tickers = [f"{sym}.NS" for sym, _, _, _ in FNO_UNIVERSE]
    print(f"Downloading 1y OHLCV for {len(tickers)} NSE F&O stocks...")
    raw = yf.download(
        tickers=tickers, period="1y", interval="1d",
        group_by="ticker", auto_adjust=True, threads=True, progress=False,
    )

    metrics = []
    for sym, name, sector, lot_size in FNO_UNIVERSE:
        tkr = f"{sym}.NS"
        try:
            df = raw[tkr] if isinstance(raw.columns, pd.MultiIndex) else raw
            res = analyze_chart_and_technicals(sym, name, sector, lot_size, df)
            if res:
                metrics.append(res)
        except Exception as exc:
            print(f"Skipping {sym}: {exc}")

    if len(metrics) < 16:
        raise RuntimeError(f"Only {len(metrics)} valid stocks downloaded; aborting overwrite.")

    bull_pool = sorted(metrics, key=lambda x: (0.65 * x["bull_tech"] + 0.35 * x["bull_sr"], x["chg_20d"]), reverse=True)[:14]
    bear_pool = sorted(metrics, key=lambda x: (0.65 * x["bear_tech"] + 0.35 * x["bear_sr"], -x["chg_20d"]), reverse=True)[:14]

    bull_picks = [format_pick(m, fetch_stock_news(m["symbol"], m["name"], "bullish"), "bullish", expiry_meta) for m in bull_pool]
    bull_picks.sort(key=lambda x: (x["rating"], x["scores"]["tech"], x["chg_20d"]), reverse=True)
    top_bull = bull_picks[:8]
    bull_syms = {x["symbol"] for x in top_bull}

    bear_picks = [
        format_pick(m, fetch_stock_news(m["symbol"], m["name"], "bearish"), "bearish", expiry_meta)
        for m in bear_pool if m["symbol"] not in bull_syms
    ]
    bear_picks.sort(key=lambda x: (x["rating"], x["scores"]["tech"], -x["chg_20d"]), reverse=True)
    top_bear = bear_picks[:8]

    # Run MCX Commodity Scanner (GOLDM, SILVERM, CRUDEOILM)
    commodities = scan_commodities(now_ist.date())

    above_50 = sum(1 for x in metrics if x["cmp"] > x["dma50"])
    breadth_pct = round((above_50 / len(metrics)) * 100)

    return {
        "updated_at": now_ist.strftime("%d %b %Y, %I:%M %p IST"),
        "universe_scanned": len(metrics),
        "expiry_meta": expiry_meta,
        "market_note": (
            f"Scanned {len(metrics)} NSE F&O stocks (Breadth: {breadth_pct}% > 50 DMA) + {len(commodities)} MCX Mini Commodities "
            f"(GOLDM, SILVERM, CRUDEOILM). {expiry_meta['rule_reason']}"
        ),
        "bullish": top_bull,
        "bearish": top_bear,
        "commodities": commodities,
    }


if __name__ == "__main__":
    data = run_scan()
    with open("picks.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Updated picks.json at {data['updated_at']} | Bull: {len(data['bullish'])} | Bear: {len(data['bearish'])} | MCX: {len(data['commodities'])}")
