"""Live data fetchers. Plumbing only; every call is cached on disk so reruns are free.

These need network access (yfinance, NSE, screener.in). If a fetch fails, callers fall
back to fixtures in data/fixtures so the demo never breaks.
"""
import json, os, time, hashlib, re

CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "cache")
os.makedirs(CACHE, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (FINN prototype)"}


def _cached(key, ttl, fn):
    path = os.path.join(CACHE, hashlib.md5(key.encode()).hexdigest() + ".json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        return json.load(open(path))
    val = fn()
    json.dump(val, open(path, "w"))
    return val


def prices(ticker: str, days: int = 60):
    """EOD close+volume via yfinance. ticker like 'RELIANCE' (NSE)."""
    def go():
        import yfinance as yf
        df = yf.Ticker(f"{ticker}.NS").history(period=f"{days}d")
        return [{"d": i.strftime("%Y-%m-%d"), "c": round(float(r.Close), 2), "v": int(r.Volume)} for i, r in df.iterrows()]
    return _cached(f"px:{ticker}:{days}", 6 * 3600, go)


def announcements(ticker: str):
    """NSE corporate announcements. NSE needs a session cookie from the homepage first."""
    def go():
        import requests
        s = requests.Session(); s.headers.update(UA)
        s.get("https://www.nseindia.com", timeout=10)
        r = s.get("https://www.nseindia.com/api/corporate-announcements",
                  params={"index": "equities", "symbol": ticker}, timeout=10)
        r.raise_for_status()
        return [{"ticker": ticker, "ts": a.get("an_dt"), "subject": a.get("desc", ""),
                 "body": a.get("attchmntText", ""), "url": a.get("attchmntFile", "")} for a in r.json()]
    return _cached(f"ann:{ticker}", 900, go)


def screener_docs(ticker: str):
    """Annual-report and concall-transcript links from screener.in's company page."""
    def go():
        import requests
        from html.parser import HTMLParser
        html = requests.get(f"https://www.screener.in/company/{ticker}/consolidated/", headers=UA, timeout=15).text
        links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]*?)\s*</a>', html)
        ar = [{"label": t, "url": u} for u, t in links if re.search(r"Financial Year", t)]
        tr = [{"label": t, "url": u} for u, t in links if "Transcript" in t]
        return {"annual_reports": ar[:5], "transcripts": tr[:6]}
    return _cached(f"scr:{ticker}", 24 * 3600, go)


def pdf_text(url: str, max_pages: int = 60):
    """Download + extract PDF text (pypdf). Cached forever: filings don't change."""
    def go():
        import requests, io
        from pypdf import PdfReader
        raw = requests.get(url, headers=UA, timeout=30).content
        rd = PdfReader(io.BytesIO(raw))
        return [(p.extract_text() or "") for p in rd.pages[:max_pages]]
    return _cached(f"pdf:{url}", 10**9, go)
