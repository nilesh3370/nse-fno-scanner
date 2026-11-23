# NSE Equity & MCX Commodity Option Seller's Scanner (v4)

Unified daily + intraday option-selling dashboard covering **60 NSE F&O stocks** AND **MCX Mini Commodities (`GOLDM`, `SILVERM`, `CRUDEOILM`)**:
- **0–100 Directional Ratings & Strength Tiers:** Strong (85+), Standard (72–84), Moderate (58–71) for both Bullish & Bearish setups
- **Global Macro + News-Safe Strikes for MCX:** Tracks COMEX Gold (`GC=F`), COMEX Silver (`SI=F`), WTI Crude (`CL=F`), USD/INR (`INR=X`), DXY (`DX-Y.NYB`), and global/Indian commodity news RSS, automatically widening OTM strike cushions during high-impact Fed/EIA/Middle East news
- **Exact MCX Multipliers & Dual-Expiry Rules:** `GOLDM` (₹10/pt), `SILVERM` (₹5/pt), `CRUDEOILM` (₹10/pt), with per-commodity expiry tracking and automatic Next-Month selection when ≤ 45 DTE
- **5 Weekday Auto-Scans** (including 7:30 PM IST peak US/MCX evening session) + browser **Run Live Scan** trigger

## Update Your Existing GitHub Repo
Extract all files flat into your repo root (replacing v3 files), then run:
```bash
git add -A
git commit -m "Upgrade to v4: add MCX GOLDM, SILVERM, CRUDEOILM with global trends, news-safe strikes & charts"
git push origin main
```
