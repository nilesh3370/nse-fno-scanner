# NSE F&O Daily Option Seller's Scanner

Automated daily NSE F&O directional scanner (Top 5 Bullish Put-Selling + Top 5 Bearish Call-Selling setups) powered by GitHub Actions + GitHub Pages at $0/month.

## 3-Minute Deployment

1. **Create a Public GitHub Repository** (e.g., `nse-fno-scanner`) — leave it empty (do not initialize with README).
2. **Push this folder to GitHub** (using `git` ensures the hidden `.github/workflows/daily_scan.yml` file is included):
   ```bash
   cd nse-fno-scanner
   git init
   git add .
   git commit -m "Initial NSE F&O daily scanner"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/nse-fno-scanner.git
   git push -u origin main
   ```
3. **Enable GitHub Pages:**
   - Open your repo on GitHub -> **Settings** -> **Pages**
   - Source: **Deploy from a branch** -> Branch: `main` / `/ (root)` -> **Save**
4. **Run Your First Live Scan:**
   - Open **Actions** -> **Daily NSE F&O Scan** -> **Run workflow**
   - Open `https://YOUR-USERNAME.github.io/nse-fno-scanner/` in any browser or phone.

Every weekday at **8:15 AM IST**, GitHub Actions automatically refreshes `picks.json` and updates your live dashboard.
