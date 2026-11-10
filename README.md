# FINN: a filter-first investing agent (mobile-first prototype)

Open `index.html` on a phone (or host it on GitHub Pages/Netlify). No backend needed for the demo.

## What works
- **Push / digest:** announcements classified (rules-first), scored 0-100, split into *needs you* / *worth a skim* / *routine (collapsed)*. Window picker: 24h, 3d, 7d.
- **Push / alerts:** user-set thresholds (volume multiple, ±% move) and filing-type watchlist, recomputed live as you drag the sliders.
- **Showcase cards:** quarterly results (Revenue, EBITDA, PBT, PAT, QoQ and YoY, margin change) and management change (bio block).
- **Pull:** promised-vs-delivered from concalls, with a verbatim quote on every row.

## Be clear about what is real
- The hosted demo runs on **SAMPLE DATA** (badge shown in the UI): seeded synthetic prices, invented filings, invented results and guidance numbers. It exists so the demo never breaks if NSE/Yahoo/screener.in block requests.
- **Written but not run end-to-end in my build environment** (it had no internet): `finn/sources.py` (yfinance, NSE, screener.in, PDF text) and `finn/pull.py` (LLM extraction). Set `FINN_LIVE=1 python build.py` and `ANTHROPIC_API_KEY=... python -m finn.pull TICKER` on a networked machine and expect to debug selectors (NSE and screener.in change markup).
- Management-change bio is a fixture; the live version (LinkedIn lookup) is not built.

## Architecture and cost
rules classifier (free) -> LLM only for low-confidence items; regex pre-filter keeps only guidance-like transcript chunks; Haiku-class model for extraction, one stronger call for the final verdict over structured claims; every fetch cached to `data/cache`. Pull prompt forbids outside knowledge and requires quotes.

## Run
```
pip install -r requirements.txt
python run.py          # sample data, serves on :8000
python run.py --live   # live prices + NSE filings (needs internet)
# Groq quick start: export GROQ_API_KEY=gsk_...   (PowerShell: $env:GROQ_API_KEY="gsk_...")
# Groq models: llama-3.1-8b-instant (bulk) + llama-3.3-70b-versatile (verdict); free tier ~30 req/min,
# so calls are paced (FINN_PAUSE, default 2.5s) and 429s retry automatically.
# free LLM options for the Ask tab (pick one):
#   Gemini: key at aistudio.google.com -> GEMINI_API_KEY
#   Groq:   key at console.groq.com    -> GROQ_API_KEY
#   Ollama: install from ollama.com, `ollama pull llama3.1`, no key
python -m finn.pull TCS   # then python build.py
```
Older commands:
```
python build.py            # sample data
FINN_LIVE=1 python build.py
python -m pytest tests
```

## Left out / next
Real LinkedIn enrichment, results-PDF table parsing end to end, remaining 7 pull views, push notifications (Expo), per-user portfolio upload.
