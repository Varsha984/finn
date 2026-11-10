"""Build index.html. Uses LIVE data if reachable (FINN_LIVE=1), else SAMPLE fixtures.

SAMPLE data is synthetic (seeded random walk, invented filings/numbers) and is labelled as
such in the UI. It exists so the demo always runs, even when NSE/Yahoo/screener block us.
"""
import json, os, random, sys
from datetime import datetime, timedelta
from finn import classify, alerts, sources
from finn.results import headline

PORTFOLIO = {  # ticker: (name, sector, base price)
    "RELIANCE": ("Reliance Industries", "Energy/Conglomerate", 2900), "TCS": ("TCS", "IT", 4100),
    "HDFCBANK": ("HDFC Bank", "Banks", 1700), "INFY": ("Infosys", "IT", 1800),
    "ITC": ("ITC", "FMCG", 470), "SUNPHARMA": ("Sun Pharma", "Pharma", 1750),
    "TATAMOTORS": ("Tata Motors", "Auto", 960), "LT": ("Larsen & Toubro", "Capital goods", 3600),
    "BHARTIARTL": ("Bharti Airtel", "Telecom", 1650), "ASIANPAINT": ("Asian Paints", "Consumer", 2400),
    "MARUTI": ("Maruti Suzuki", "Auto", 12500), "ADANIPORTS": ("Adani Ports", "Infra", 1400),
    "ZOMATO": ("Zomato", "Internet", 260), "DIXON": ("Dixon Technologies", "Electronics", 15500),
    "PERSISTENT": ("Persistent Systems", "IT midcap", 5800), "KPITTECH": ("KPIT Technologies", "Auto-tech", 1300),
}

# (ticker, hours_ago, subject, body, extra)
ANN = [
 ("TCS", 3, "Outcome of Board Meeting - Financial Results for the quarter ended September 30", "Board approved unaudited results.", "results"),
 ("DIXON", 5, "Appointment of Chief Financial Officer", "Board approved appointment of new CFO effective Dec 1.", "mgmt"),
 ("TATAMOTORS", 7, "Investor Presentation - Q2 results", "Presentation to analysts.", None),
 ("ADANIPORTS", 9, "Receipt of show cause notice from tax authority", "Demand of Rs 412 crore under review.", None),
 ("RELIANCE", 11, "Acquisition of 100% stake in a renewable subsidiary", "Definitive agreement executed.", None),
 ("ITC", 12, "Declaration of interim dividend and record date", "Rs 7.50/share; record date Nov 14.", None),
 ("HDFCBANK", 14, "Credit rating reaffirmed by CRISIL - AAA/Stable", "", None),
 ("INFY", 15, "Allotment of equity shares under ESOP", "", None),
 ("MARUTI", 17, "Newspaper publication - results advertisement", "", None),
 ("SUNPHARMA", 19, "Press release: US FDA approval for generic", "", None),
 ("KPITTECH", 21, "Schedule of analyst / institutional investor meets", "", None),
 ("ZOMATO", 22, "Promoter pledge invocation disclosure", "Lender invoked pledge on 0.4% of holding.", None),
 ("LT", 26, "Bags order worth Rs 5,000 crore - clarification", "", None),
 ("PERSISTENT", 30, "Trading window closure intimation", "", None),
 ("BHARTIARTL", 34, "Resignation of Independent Director", "Cited other commitments.", None),
 ("ASIANPAINT", 40, "Approval of capex for new plant - capacity expansion", "Rs 2,100 crore over 3 years.", None),
 ("INFY", 52, "Compliance certificate under Regulation 74(5)", "", None),
 ("ZOMATO", 60, "Notice of Postal Ballot", "", None),
 ("TCS", 80, "Transcript of earnings call - Q2", "", None),
 ("RELIANCE", 120, "Credit rating upgrade by ICRA", "", None),
 ("DIXON", 150, "Notice of Annual General Meeting", "", None),
]

RESULTS = {  # Rs crore, SAMPLE numbers
 "TCS": ({"revenue": 64800, "ebitda": 17000, "pbt": 16100, "pat": 12150},
         {"revenue": 63500, "ebitda": 16500, "pbt": 15700, "pat": 11800},
         {"revenue": 59700, "ebitda": 15400, "pbt": 14600, "pat": 11000}),
}
MGMT = {"DIXON": {"person": "Priya Menon (sample)", "role": "Chief Financial Officer", "bio": "SAMPLE: 18 yrs in manufacturing finance; previously Group CFO at a listed electronics maker and VP Finance at a global EMS firm. Chartered Accountant. Source for live version: LinkedIn / public profile lookup."}}

PVD = {"TCS": {"note": "SAMPLE fixture - run `python -m finn.pull TICKER` for live extraction", "rows": [
  {"metric": "Operating margin", "said": "Aim to return to the 26-28% band", "call": "Q2 FY26", "got": "24.5%", "status": "miss", "quote": "SAMPLE: \"we continue to target our band of 26 to 28 percent\""},
  {"metric": "Net headcount", "said": "Hiring to resume from H2", "call": "Q3 FY26", "got": "Flat QoQ", "status": "miss", "quote": "SAMPLE: \"we expect hiring to pick up in the second half\""},
  {"metric": "Deal TCV", "said": "Pipeline healthy, large deals closing", "call": "Q4 FY26", "got": "Record TCV", "status": "met", "quote": "SAMPLE: \"the pipeline is the strongest we have seen\""},
  {"metric": "Capex", "said": "~2% of revenue", "call": "Q1 FY27", "got": "1.8%", "status": "met", "quote": "SAMPLE: \"capex should stay around two percent\""},
]}}


def sample_prices(seed, base):
    rnd = random.Random(seed); px = base; rows = []
    d = datetime.now().date() - timedelta(days=45)
    while len(rows) < 32:
        d += timedelta(days=1)
        if d.weekday() >= 5: continue
        px *= 1 + rnd.gauss(0, 0.011); rows.append({"d": str(d), "c": round(px, 2), "v": int(rnd.gauss(2e6, 3e5))})
    return rows


def load_pvd():
    out = dict(PVD)
    d = os.path.join("data", "pvd")
    if os.path.isdir(d):
        for f in os.listdir(d):
            rows = json.load(open(os.path.join(d, f)))
            out[f[:-5]] = {"note": "Live extraction from concall transcripts", "rows": rows}
    return out


def main():
    now = datetime.now()
    live = os.getenv("FINN_LIVE") == "1"
    prices = {}
    for i, (t, (n, s, b)) in enumerate(PORTFOLIO.items()):
        try:
            if not live: raise RuntimeError
            prices[t] = sources.prices(t)
        except Exception:
            prices[t] = sample_prices(i + 7, b)
    # inject demo-able unusual moves into SAMPLE data
    for t, vm, ch in (("ZOMATO", 3.4, -5.8), ("ADANIPORTS", 2.6, -2.1), ("DIXON", 1.4, 4.6)):
        if not live:
            r = prices[t]; r[-1]["c"] = round(r[-2]["c"] * (1 + ch / 100), 2); r[-1]["v"] = int(2e6 * vm)

    ann = ANN
    if live:
        ann = []
        for t in PORTFOLIO:
            try:
                for a in sources.announcements(t):
                    ts = datetime.strptime(a["ts"], "%d-%b-%Y %H:%M:%S")
                    h = (now - ts).total_seconds() / 3600
                    if 0 <= h <= 168:
                        ann.append((t, round(h), a["subject"], a["body"] or "", None))
            except Exception as e:
                print(f"announcements failed for {t}: {e}")
        if not ann:
            print("no live announcements, using sample"); ann = ANN
    items = []
    for t, h, subj, body, extra in ann:
        cat = classify.classify(subj, body); p = classify.priority(cat, subj, body)
        it = {"ticker": t, "hours_ago": h, "ts": (now - timedelta(hours=h)).isoformat(timespec="minutes"),
              "subject": subj, "cat": cat, "p": p, "tier": classify.tier(p), "body": body}
        if cat == "results" and t in RESULTS: it["results"] = headline(*RESULTS[t])
        if cat == "management_change" and t in MGMT: it["mgmt"] = MGMT[t]
        items.append(it)
    items.sort(key=lambda x: -x["p"])

    data = {"asof": now.isoformat(timespec="minutes"), "live": live and True, "defaults": alerts.DEFAULTS,
            "portfolio": {t: {"name": n, "sector": s} for t, (n, s, _) in PORTFOLIO.items()},
            "prices": {t: r[-26:] for t, r in prices.items()}, "ann": items, "pvd": load_pvd()}
    html = open("app.html").read().replace("/*__DATA__*/null", json.dumps(data))
    open("index.html", "w").write(html)
    json.dump(data, open("data.json", "w"))
    print(f"built index.html: {len(items)} announcements, {len(prices)} tickers, live={data['live']}")


if __name__ == "__main__":
    main()
