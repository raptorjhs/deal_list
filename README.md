# Deal List — deploy

Static list site. `deals.json` is the database. GitHub Pages serves it. GitHub Actions updates the JSON.

## Files to upload

```
index.html
styles.css
app.js
deals.json
scrape_wsj_ma.py
README.md
.github/workflows/update-deals.yml
```

Do not add a backend, login, or extra pages.

## Deploy on GitHub Pages

1. Create a public repo, e.g. `deal-list`.
2. Upload the files above so they sit at the **repo root** (not inside another folder).
3. Settings → Pages
   - Source: **Deploy from a branch**
   - Branch: `main`
   - Folder: `/ (root)`
4. Settings → Actions → General
   - Allow Actions
   - Workflow permissions: **Read and write**
5. Site URL: `https://YOUR_USER.github.io/deal-list/`

First visit may take 1–2 minutes after Pages is enabled.

## Automatic JSON updates

The workflow `.github/workflows/update-deals.yml`:

- runs every Friday at 18:40 HKT (10:40 UTC)
- can also be started by hand: Actions → Update deals → Run workflow
- runs `python scrape_wsj_ma.py --output deals.json`
- merges new WSJ M&A headlines into `deals.json` (no duplicate headlines)
- commits and pushes only if the file changed
- Pages rebuilds the live table

## Local test

```bash
python scrape_wsj_ma.py --output deals.json
python3 -m http.server 8765
```

Open http://127.0.0.1:8765/

## JSON row the site expects

```json
{
  "company_a": "J&J",
  "company_b": "Apollo",
  "headline": "J&J Is in Talks to Sell Its Hips-and-Knees Business to Apollo for $20 Billion",
  "link": "https://news.google.com/search?q=%22J%26J%22%20%22Apollo%22&hl=en-US&gl=US&ceid=US:en",
  "time": "2026-09-12T19:40:00+00:00"
}
```

The table uses `company_a / company_b` as the name, `link` as the name URL, `headline` as Summary, and `time` as the date.
