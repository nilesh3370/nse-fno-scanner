"""
NSE F&O Daily Option Seller's Scanner
Screens ~55 liquid NSE F&O stocks in a single batched Yahoo Finance request,
scores directional conviction, calculates support/resistance zones & credit
spread strikes, and outputs picks.json for index.html.
"""

import json
import math
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import yfinance as yf

# Curated liquid NSE F&O universe: (NSE_SYMBOL, Display Name, Sector, Approx Lot Size)
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
    ("BHARTIARTL", "Bharti Airtel Ltd.", "Telecom", 475),
    ("LT", "Larsen & Toubro", "Infrastructure", 150),
    ("ITC", "ITC Ltd.", "FMCG", 1600),
    ("HINDUNILVR", "Hindustan Unilever", "FMCG", 300),
    ("MARICO", "Marico Ltd.", "FMCG", 1200),
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
]


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


def analyze_stock(symbol: str, name: str, sector: str, lot_size: int, df: pd.DataFrame):
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

    # --- Bullish Conviction Score (0-100) ---
    bull_score = 40.0
    if cmp > dma20:
        bull_score += 10
    if cmp > dma50:
        bull_score += 12
    if cmp > dma200:
        bull_score += 10
    if dma20 > dma50 > dma200:
        bull_score += 8
    if dist_52w_high >= -5.0:
        bull_score += 10
    elif dist_52w_high >= -10.0:
        bull_score += 5
    if 54 <= rsi <= 74:
        bull_score += 8
    elif rsi > 74:
        bull_score += 3  # Strong trend, slight overbought caution
    if chg_20d > 3.0:
        bull_score += min(10.0, chg_20d * 0.8)
    if vol_ratio > 1.15 and chg_20d > 0:
        bull_score += 4
    bull_score = max(0, min(98, int(round(bull_score))))

    # --- Bearish Conviction Score (0-100) ---
    bear_score = 40.0
    if cmp < dma20:
        bear_score += 10
    if cmp < dma50:
        bear_score += 12
    if cmp < dma200:
        bear_score += 10
    if dma20 < dma50 < dma200:
        bear_score += 8
    if dist_52w_high <= -15.0:
        bear_score += 8
    if dist_52w_low <= 12.0:
        bear_score += 6
    if 26 <= rsi <= 46:
        bear_score += 8
    elif rsi < 26:
        bear_score += 3  # Deeply oversold bounce risk
    if chg_20d < -3.0:
        bear_score += min(10.0, abs(chg_20d) * 0.8)
    if vol_ratio > 1.15 and chg_20d < 0:
        bear_score += 4
    bear_score = max(0, min(98, int(round(bear_score))))

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
        "bull_score": bull_score,
        "bear_score": bear_score,
        "swing_low_20": float(df["Low"].tail(20).min()),
        "swing_high_20": float(df["High"].tail(20).max()),
    }


def format_pick(m: dict, bias: str) -> dict:
    cmp = m["cmp"]
    step = strike_step(cmp)
    atr = m["atr"]

    if bias == "bullish":
        # Anchor support near max(20D swing low, cmp - 1.8*ATR, dma50) capped below cmp
        raw_support = min(cmp * 0.96, max(m["swing_low_20"], cmp - 2.0 * atr))
        short_strike = round_to_step(raw_support, step, "down")
        if short_strike >= cmp * 0.975:
            short_strike = round_to_step(cmp * 0.955, step, "down")
        spread_width = max(step * 2, round_to_step(cmp * 0.035, step, "nearest"))
        hedge_strike = max(step, short_strike - spread_width)
        zone_low = round_to_step(short_strike - step, step, "down")
        zone_high = round_to_step(min(cmp * 0.98, short_strike + step), step, "nearest")
        invalidation = round(zone_low * 0.985, 1)
        est_credit = round(max(1.0, spread_width * 0.28), 1)

        tech_reason = (
            f"Trading at {fmt_inr(cmp)} ({m['dist_52w_high']:+.1f}% from 52W high {fmt_inr(m['high_52w'])}), "
            f"above 50 DMA ({fmt_inr(m['dma50'])}) and 200 DMA ({fmt_inr(m['dma200'])})."
        )
        mom_reason = (
            f"Up {m['chg_20d']:+.1f}% over 20 sessions with RSI(14) at {m['rsi']} and "
            f"{m['vol_ratio']:.2f}x 20-day volume participation in {m['sector']}."
        )
        if m["rsi"] > 72:
            risk_reason = f"RSI ({m['rsi']}) is slightly stretched; prefer Bull Put Spread below {fmt_inr(short_strike)} and avoid aggressive ATM selling."
        elif m["atr_pct"] > 2.8:
            risk_reason = f"Elevated daily ATR ({m['atr_pct']:.1f}%); keep hedge active at {fmt_inr(hedge_strike)} and monitor close below {fmt_inr(invalidation)}."
        else:
            risk_reason = f"Controlled volatility (ATR {m['atr_pct']:.1f}%); exit or adjust spread if daily close breaks {fmt_inr(invalidation)}."

        return {
            "symbol": m["symbol"],
            "name": m["name"],
            "sector": m["sector"],
            "bias": "bullish",
            "strategy": "Bull Put Spread / OTM Put Sell",
            "cmp": cmp,
            "chg_1d": m["chg_1d"],
            "chg_20d": m["chg_20d"],
            "rsi": m["rsi"],
            "dma50": m["dma50"],
            "dma200": m["dma200"],
            "dist_52w_high": m["dist_52w_high"],
            "vol_ratio": m["vol_ratio"],
            "conviction": m["bull_score"],
            "zone_label": "Support Zone",
            "zone": f"{fmt_inr(zone_low)} – {fmt_inr(zone_high)}",
            "invalidation": invalidation,
            "short_strike": short_strike,
            "hedge_strike": hedge_strike,
            "est_credit": est_credit,
            "lot_size": m["lot_size"],
            "reasons": {
                "technical": tech_reason,
                "fundamental": mom_reason,
                "risk": risk_reason,
            },
        }
    else:
        raw_res = max(cmp * 1.045, min(m["swing_high_20"], cmp + 2.2 * atr))
        short_strike = round_to_step(raw_res, step, "up")
        if short_strike <= cmp * 1.025:
            short_strike = round_to_step(cmp * 1.05, step, "up")
        spread_width = max(step * 2, round_to_step(cmp * 0.035, step, "nearest"))
        hedge_strike = short_strike + spread_width
        zone_low = round_to_step(max(cmp * 1.02, short_strike - step), step, "nearest")
        zone_high = round_to_step(short_strike + step, step, "up")
        invalidation = round(zone_high * 1.015, 1)
        est_credit = round(max(1.0, spread_width * 0.28), 1)

        tech_reason = (
            f"Weak trend at {fmt_inr(cmp)} ({m['dist_52w_high']:+.1f}% off 52W high), "
            f"pressured below 50 DMA ({fmt_inr(m['dma50'])}) and 200 DMA ({fmt_inr(m['dma200'])})."
        )
        mom_reason = (
            f"Down {m['chg_20d']:+.1f}% over 20 sessions with bearish RSI(14) at {m['rsi']} "
            f"and {m['vol_ratio']:.2f}x recent volume in {m['sector']}."
        )
        if m["rsi"] < 30:
            risk_reason = f"Oversold RSI ({m['rsi']}) increases short-covering bounce risk; sell calls on rallies and cap upside at {fmt_inr(hedge_strike)}."
        else:
            risk_reason = f"Daily ATR is {m['atr_pct']:.1f}%; verify NSE F&O ban (MWPL) status and exit if price closes above {fmt_inr(invalidation)}."

        return {
            "symbol": m["symbol"],
            "name": m["name"],
            "sector": m["sector"],
            "bias": "bearish",
            "strategy": "Bear Call Spread / OTM Call Sell",
            "cmp": cmp,
            "chg_1d": m["chg_1d"],
            "chg_20d": m["chg_20d"],
            "rsi": m["rsi"],
            "dma50": m["dma50"],
            "dma200": m["dma200"],
            "dist_52w_high": m["dist_52w_high"],
            "vol_ratio": m["vol_ratio"],
            "conviction": m["bear_score"],
            "zone_label": "Resistance Zone",
            "zone": f"{fmt_inr(zone_low)} – {fmt_inr(zone_high)}",
            "invalidation": invalidation,
            "short_strike": short_strike,
            "hedge_strike": hedge_strike,
            "est_credit": est_credit,
            "lot_size": m["lot_size"],
            "reasons": {
                "technical": tech_reason,
                "fundamental": mom_reason,
                "risk": risk_reason,
            },
        }


def run_scan() -> dict:
    tickers = [f"{sym}.NS" for sym, _, _, _ in FNO_UNIVERSE]
    print(f"Downloading 1y daily data for {len(tickers)} NSE F&O stocks...")
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
            if isinstance(raw.columns, pd.MultiIndex):
                if tkr not in raw.columns.get_level_values(0):
                    continue
                df = raw[tkr]
            else:
                df = raw
            res = analyze_stock(sym, name, sector, lot_size, df)
            if res:
                metrics.append(res)
        except Exception as exc:
            print(f"Skipping {sym}: {exc}")

    if len(metrics) < 10:
        raise RuntimeError(f"Only {len(metrics)} valid stocks downloaded; aborting overwrite.")

    # Rank top 5 bullish (must have positive bias & above 50 DMA preference)
    bull_sorted = sorted(
        metrics,
        key=lambda x: (x["bull_score"], x["chg_20d"], x["vol_ratio"]),
        reverse=True,
    )
    top_bull_raw = bull_sorted[:5]
    bull_syms = {x["symbol"] for x in top_bull_raw}

    # Rank top 5 bearish (disjoint from bullish)
    bear_candidates = [x for x in metrics if x["symbol"] not in bull_syms]
    bear_sorted = sorted(
        bear_candidates,
        key=lambda x: (x["bear_score"], -x["chg_20d"], x["vol_ratio"]),
        reverse=True,
    )
    top_bear_raw = bear_sorted[:5]

    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    above_50 = sum(1 for x in metrics if x["cmp"] > x["dma50"])
    breadth_pct = round((above_50 / len(metrics)) * 100)

    payload = {
        "updated_at": now_ist.strftime("%d %b %Y, %I:%M %p IST"),
        "series": now_ist.strftime("%B %Y Monthly F&O"),
        "universe_scanned": len(metrics),
        "market_note": (
            f"Scanned {len(metrics)} liquid NSE F&O stocks. Market breadth: {breadth_pct}% trading above 50 DMA. "
            "Verify live option chain IV, liquidity, and NSE MWPL ban list before entering trades."
        ),
        "bullish": [format_pick(x, "bullish") for x in top_bull_raw],
        "bearish": [format_pick(x, "bearish") for x in top_bear_raw],
    }
    return payload


if __name__ == "__main__":
    data = run_scan()
    with open("picks.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Successfully updated picks.json at {data['updated_at']}")
