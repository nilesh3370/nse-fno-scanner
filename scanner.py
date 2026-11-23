"""
NSE F&O Daily Option Seller's Scanner (News + Technicals + Dual-Expiry Engine)
- Screens 60 liquid NSE F&O stocks via batched Yahoo Finance OHLCV data
- Fetches live Indian financial news headlines via Google News RSS + yfinance
- Scores Composite Conviction = 65% Technicals + 35% News Catalyst Sentiment
- Calculates BOTH Current Month & Next Month NSE expiries (Last Tuesday rule + NSE holidays)
- Automatically recommends Next Month Expiry whenever Next Expiry DTE <= 45 days
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

# NSE Trading Holidays (2026 - 2027) used to shift Tuesday expiries to prior trading day
NSE_HOLIDAYS = {
    date(2026, 1, 15),
    date(2026, 1, 26),
    date(2026, 3, 3),
    date(2026, 3, 26),
    date(2026, 3, 31),
    date(2026, 4, 3),
    date(2026, 4, 14),
    date(2026, 5, 1),
    date(2026, 5, 28),
    date(2026, 6, 26),
    date(2026, 9, 14),
    date(2026, 10, 2),
    date(2026, 10, 20),
    date(2026, 11, 10),
    date(2026, 11, 24),  # Guru Nanak Jayanti -> shifts Nov 2026 expiry to Mon 23 Nov
    date(2026, 12, 25),
    date(2027, 1, 26),   # Republic Day -> shifts Jan 2027 expiry to Mon 25 Jan
    date(2027, 3, 26),
    date(2027, 4, 14),
    date(2027, 8, 15),
    date(2027, 10, 2),
    date(2027, 12, 25),
}

# 60 High-Liquidity NSE F&O Stocks: (NSE_SYMBOL, Full Name, Sector, Approx Lot Size)
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
    ("ABB", "ABB India Ltd.", "Capital Goods", 125),
    ("DLF", "DLF Ltd.", "Real Estate", 825),
    ("PAGEIND", "Page Industries", "Apparel", 15),
    ("ADANIENT", "Adani Enterprises", "Conglomerate", 300),
    ("ADANIPORTS", "Adani Ports & SEZ", "Infrastructure", 400),
    ("CHOLAFIN", "Cholamandalam Inv.", "NBFC", 625),
    ("POLYCAB", "Polycab India Ltd.", "Cables & Wires", 125),
]

POSITIVE_KEYWORDS = {
    "surge": 2.5, "surges": 2.5, "rally": 2.2, "rallies": 2.2, "all-time high": 3.0,
    "record high": 2.8, "52-week high": 2.5, "breakout": 2.2, "profit jump": 2.8,
    "profit surges": 2.8, "beats estimates": 2.8, "beat estimates": 2.8, "strong q": 2.0,
    "upgrade": 2.5, "upgrades": 2.5, "buy rating": 2.4, "target price": 1.6,
    "order win": 2.6, "wins order": 2.6, "contract win": 2.5, "bagged order": 2.5,
    "buyback": 2.4, "dividend": 1.6, "expansion": 1.8, "approval": 2.0,
    "margin expansion": 2.4, "robust": 1.8, "outperform": 2.2, "momentum": 1.5,
    "clarifies": 1.2, "secure": 1.2, "growth": 1.4,
}

NEGATIVE_KEYWORDS = {
    "plunge": -3.0, "plunges": -3.0, "slump": -2.8, "slumps": -2.8, "tumble": -2.6,
    "tumbles": -2.6, "crash": -3.0, "falls": -2.0, "fall": -1.8, "drops": -2.0,
    "drop": -1.8, "downgrade": -2.6, "downgrades": -2.6, "sell rating": -2.6,
    "cut target": -2.4, "cuts target": -2.4, "misses estimates": -2.8, "miss": -2.2,
    "loss": -2.2, "profit falls": -2.6, "profit drops": -2.6, "margin pressure": -2.4,
    "weak demand": -2.2, "sluggish": -2.0, "sebi": -2.2, "probe": -2.5,
    "penalty": -2.4, "fraud": -3.0, "default": -3.0, "open offer": -1.5,
    "stake sale": -1.8, "block deal": -1.2, "overhang": -2.0, "breakdown": -2.2,
    "drags": -1.8, "underperform": -2.2, "de-rating": -2.4,
}


def get_nse_monthly_expiry(year: int, month: int) -> date:
    """NSE stock & index monthly expiry = last Tuesday of the month, shifted back on holidays."""
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() != 1:
        d -= timedelta(days=1)
    while d.weekday() >= 5 or d in NSE_HOLIDAYS:
        d -= timedelta(days=1)
    return d


def compute_expiry_schedule(today: date) -> dict:
    """
    Returns Current Month expiry and Next Month expiry with DTE,
    plus auto-recommendation: if next_expiry_dte <= 45, recommend Next Month!
    """
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
            f"recommending Next Month Expiry for optimal theta decay and lower expiry-week gamma risk."
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


def analyze_technicals(symbol: str, name: str, sector: str, lot_size: int, df: pd.DataFrame):
    df = df.dropna(subset=["Close", "High", "Low", "Volume"]).copy()
    if len(df) < 60:
        return None

    close = df["Close"]
    cmp = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    chg_1d = ((cmp - prev_close) / prev_close) * 100.0

    idx_20 = max(0, len(close) - 21)
    chg_20d = ((cmp - float(close.iloc[idx_20])) / float(close.iloc[idx_20])) * 100.0

    dma20 = float(close.tail(20).mean())
    dma50 = float(close.tail(50).mean())
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

    bull_tech = 35.0
    if cmp > dma20:
        bull_tech += 12
    if cmp > dma50:
        bull_tech += 14
    if cmp > dma200:
        bull_tech += 12
    if dma20 > dma50 > dma200:
        bull_tech += 8
    if dist_52w_high >= -5.0:
        bull_tech += 10
    elif dist_52w_high >= -10.0:
        bull_tech += 5
    if 54 <= rsi <= 75:
        bull_tech += 8
    elif rsi > 75:
        bull_tech += 3
    if chg_20d > 3.0:
        bull_tech += min(10.0, chg_20d * 0.7)
    if vol_ratio > 1.15 and chg_20d > 0:
        bull_tech += 4
    bull_tech = max(0, min(98, int(round(bull_tech))))

    bear_tech = 35.0
    if cmp < dma20:
        bear_tech += 12
    if cmp < dma50:
        bear_tech += 14
    if cmp < dma200:
        bear_tech += 12
    if dma20 < dma50 < dma200:
        bear_tech += 8
    if dist_52w_high <= -15.0:
        bear_tech += 8
    if dist_52w_low <= 12.0:
        bear_tech += 6
    if 25 <= rsi <= 46:
        bear_tech += 8
    elif rsi < 25:
        bear_tech += 3
    if chg_20d < -3.0:
        bear_tech += min(10.0, abs(chg_20d) * 0.7)
    if vol_ratio > 1.15 and chg_20d < 0:
        bear_tech += 4
    bear_tech = max(0, min(98, int(round(bear_tech))))

    return {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "lot_size": lot_size,
        "cmp": round(cmp, 2),
        "chg_1d": round(chg_1d, 2),
        "chg_20d": round(chg_20d, 2),
        "rsi": round(rsi, 1),
        "dma20": round(dma20, 2),
        "dma50": round(dma50, 2),
        "dma200": round(dma200, 2),
        "atr": round(atr, 2),
        "atr_pct": round(atr_pct, 2),
        "high_52w": round(high_52w, 2),
        "dist_52w_high": round(dist_52w_high, 2),
        "vol_ratio": round(vol_ratio, 2),
        "bull_tech": bull_tech,
        "bear_tech": bear_tech,
        "swing_low_20": float(df["Low"].tail(20).min()),
        "swing_high_20": float(df["High"].tail(20).max()),
    }


def fetch_stock_news(symbol: str, company_name: str, bias: str) -> dict:
    """
    Fetches recent headlines via Google News RSS (en-IN) with yfinance fallback,
    and scores news catalyst alignment with the directional bias.
    """
    headlines = []
    query = urllib.parse.quote(f'"{company_name}" OR "{symbol}" NSE stock')
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

    try:
        req = urllib.request.Request(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NSEFnOScanner/2.0)"},
        )
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
                    "title": raw_title,
                    "source": source_name,
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
        annotated.append({
            "title": h["title"],
            "source": h["source"],
            "sentiment": sent_tag,
            "url": h["url"],
        })

    aligned_signal = raw_polarity if bias == "bullish" else -raw_polarity
    news_score = int(max(25, min(96, round(68 + aligned_signal * 5.0))))

    if not annotated:
        news_summary = f"No adverse corporate shock flagged; sector & institutional momentum in {symbol} remains intact."
        sentiment_label = "Neutral / Clean Tape"
    else:
        top_headline = annotated[0]["title"]
        if news_score >= 78:
            sentiment_label = "Strong Bullish Catalyst" if bias == "bullish" else "Heavy Bearish Catalyst"
            news_summary = f"Confirmed by recent news flow: \"{top_headline}\""
        elif news_score >= 60:
            sentiment_label = "Supportive News Flow" if bias == "bullish" else "Bearish Overhang"
            news_summary = f"Recent coverage aligns with trend: \"{top_headline}\""
        else:
            sentiment_label = "Mixed / Watch Headlines"
            news_summary = f"Mixed news signal—verify headline impact before sizing: \"{top_headline}\""

    return {
        "news_score": news_score,
        "sentiment_label": sentiment_label,
        "news_summary": news_summary,
        "headlines": annotated,
    }


def build_expiry_levels(m: dict, bias: str, dte: int) -> dict:
    cmp = m["cmp"]
    step = strike_step(cmp)
    atr = m["atr"]
    time_scale = max(0.35, min(1.35, math.sqrt(max(2, dte) / 30.0)))

    if bias == "bullish":
        buffer = max(cmp * (0.018 * time_scale), 1.6 * atr * time_scale)
        short_strike = round_to_step(cmp - buffer, step, "down")
        if short_strike >= cmp:
            short_strike = round_to_step(cmp - step, step, "down")
        spread_width = max(step, round_to_step(cmp * (0.025 if dte <= 15 else 0.035), step, "nearest"))
        hedge_strike = max(step, short_strike - spread_width)
        zone_low = round_to_step(short_strike - step, step, "down")
        zone_high = round_to_step(min(cmp - step * 0.5, short_strike + step * 0.5), step, "nearest")
        if zone_high <= zone_low:
            zone_high = short_strike
        invalidation = round(zone_low * 0.99, 1)
        est_credit = round(max(0.8, spread_width * (0.22 if dte <= 15 else 0.28)), 1)
        return {
            "zone": f"{fmt_inr(zone_low)} – {fmt_inr(zone_high)}",
            "invalidation": invalidation,
            "short_strike": short_strike,
            "hedge_strike": hedge_strike,
            "est_credit": est_credit,
        }
    else:
        buffer = max(cmp * (0.018 * time_scale), 1.6 * atr * time_scale)
        short_strike = round_to_step(cmp + buffer, step, "up")
        if short_strike <= cmp:
            short_strike = round_to_step(cmp + step, step, "up")
        spread_width = max(step, round_to_step(cmp * (0.025 if dte <= 15 else 0.035), step, "nearest"))
        hedge_strike = short_strike + spread_width
        zone_low = round_to_step(max(cmp + step * 0.5, short_strike - step * 0.5), step, "nearest")
        zone_high = round_to_step(short_strike + step, step, "up")
        if zone_high <= zone_low:
            zone_high = short_strike + step
        invalidation = round(zone_high * 1.01, 1)
        est_credit = round(max(0.8, spread_width * (0.22 if dte <= 15 else 0.28)), 1)
        return {
            "zone": f"{fmt_inr(zone_low)} – {fmt_inr(zone_high)}",
            "invalidation": invalidation,
            "short_strike": short_strike,
            "hedge_strike": hedge_strike,
            "est_credit": est_credit,
        }


def format_final_pick(m: dict, news_info: dict, bias: str, expiry_meta: dict) -> dict:
    tech_score = m["bull_tech"] if bias == "bullish" else m["bear_tech"]
    news_score = news_info["news_score"]
    composite = int(round(0.65 * tech_score + 0.35 * news_score))

    curr_dte = expiry_meta["current_month"]["dte"]
    next_dte = expiry_meta["next_month"]["dte"]
    curr_levels = build_expiry_levels(m, bias, curr_dte)
    next_levels = build_expiry_levels(m, bias, next_dte)
    primary_levels = next_levels if expiry_meta["recommended"] == "next" else curr_levels

    if bias == "bullish":
        tech_reason = (
            f"Trading at {fmt_inr(m['cmp'])} ({m['dist_52w_high']:+.1f}% from 52W high), "
            f"above 50 DMA ({fmt_inr(m['dma50'])}) & 200 DMA ({fmt_inr(m['dma200'])}), "
            f"20D gain {m['chg_20d']:+.1f}%, RSI(14) {m['rsi']}."
        )
        risk_reason = (
            f"Daily ATR {m['atr_pct']:.1f}% ({m['vol_ratio']:.2f}x vol). "
            f"Hedge with {fmt_inr(primary_levels['hedge_strike'])} Put; exit if daily close breaches {fmt_inr(primary_levels['invalidation'])}."
        )
        strategy = "Bull Put Spread / OTM Put Sell"
    else:
        tech_reason = (
            f"Weak trend at {fmt_inr(m['cmp'])} ({m['dist_52w_high']:+.1f}% off 52W high), "
            f"below 50 DMA ({fmt_inr(m['dma50'])}) & 200 DMA ({fmt_inr(m['dma200'])}), "
            f"20D move {m['chg_20d']:+.1f}%, RSI(14) {m['rsi']}."
        )
        risk_reason = (
            f"Daily ATR {m['atr_pct']:.1f}% ({m['vol_ratio']:.2f}x vol). "
            f"Check NSE MWPL ban list; hedge with {fmt_inr(primary_levels['hedge_strike'])} Call and exit above {fmt_inr(primary_levels['invalidation'])}."
        )
        strategy = "Bear Call Spread / OTM Call Sell"

    return {
        "symbol": m["symbol"],
        "name": m["name"],
        "sector": m["sector"],
        "bias": bias,
        "strategy": strategy,
        "cmp": m["cmp"],
        "chg_1d": m["chg_1d"],
        "chg_20d": m["chg_20d"],
        "rsi": m["rsi"],
        "dma50": m["dma50"],
        "dma200": m["dma200"],
        "dist_52w_high": m["dist_52w_high"],
        "vol_ratio": m["vol_ratio"],
        "tech_score": tech_score,
        "news_score": news_score,
        "conviction": composite,
        "news_sentiment": news_info["sentiment_label"],
        "expiries": {
            "current": curr_levels,
            "next": next_levels,
        },
        "lot_size": m["lot_size"],
        "reasons": {
            "technical": tech_reason,
            "news": news_info["news_summary"],
            "risk": risk_reason,
        },
        "headlines": news_info["headlines"],
    }


def run_scan() -> dict:
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    expiry_meta = compute_expiry_schedule(now_ist.date())

    tickers = [f"{sym}.NS" for sym, _, _, _ in FNO_UNIVERSE]
    print(f"Downloading 1y daily data for {len(tickers)} liquid NSE F&O stocks...")
    raw = yf.download(
        tickers=tickers,
        period="1y",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    metrics = []
    for sym, name, sector, lot_size in FNO_UNIVERSE:
        tkr = f"{sym}.NS"
        try:
            df = raw[tkr] if isinstance(raw.columns, pd.MultiIndex) else raw
            res = analyze_technicals(sym, name, sector, lot_size, df)
            if res:
                metrics.append(res)
        except Exception as exc:
            print(f"Skipping {sym}: {exc}")

    if len(metrics) < 12:
        raise RuntimeError(f"Only {len(metrics)} valid stocks downloaded; aborting overwrite.")

    bull_pool = sorted(metrics, key=lambda x: (x["bull_tech"], x["chg_20d"]), reverse=True)[:14]
    bear_pool = sorted(metrics, key=lambda x: (x["bear_tech"], -x["chg_20d"]), reverse=True)[:14]

    print("Fetching live news headlines & sentiment for top technical candidates...")
    bull_picks = []
    for m in bull_pool:
        n_info = fetch_stock_news(m["symbol"], m["name"], "bullish")
        bull_picks.append(format_final_pick(m, n_info, "bullish", expiry_meta))

    bull_picks.sort(key=lambda x: (x["conviction"], x["news_score"], x["chg_20d"]), reverse=True)
    top_bull = bull_picks[:5]
    bull_syms = {x["symbol"] for x in top_bull}

    bear_picks = []
    for m in bear_pool:
        if m["symbol"] in bull_syms:
            continue
        n_info = fetch_stock_news(m["symbol"], m["name"], "bearish")
        bear_picks.append(format_final_pick(m, n_info, "bearish", expiry_meta))

    bear_picks.sort(key=lambda x: (x["conviction"], x["news_score"], -x["chg_20d"]), reverse=True)
    top_bear = bear_picks[:5]

    above_50 = sum(1 for x in metrics if x["cmp"] > x["dma50"])
    breadth_pct = round((above_50 / len(metrics)) * 100)

    return {
        "updated_at": now_ist.strftime("%d %b %Y, %I:%M %p IST"),
        "universe_scanned": len(metrics),
        "expiry_meta": expiry_meta,
        "market_note": (
            f"News + Technical hybrid scan across {len(metrics)} liquid NSE F&O stocks "
            f"(Market breadth: {breadth_pct}% above 50 DMA). {expiry_meta['rule_reason']}"
        ),
        "bullish": top_bull,
        "bearish": top_bear,
    }


if __name__ == "__main__":
    data = run_scan()
    with open("picks.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Updated picks.json at {data['updated_at']} | Recommended series: {data['expiry_meta']['recommended']}")
