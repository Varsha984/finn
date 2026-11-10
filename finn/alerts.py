"""Configurable unusual-move detection on end-of-day data."""
from statistics import mean

DEFAULTS = {"vol_mult": 2.0, "price_pct": 4.0, "lookback": 20}


def unusual(rows, vol_mult=2.0, price_pct=4.0, lookback=20):
    """rows: list of {d, c, v} oldest->newest. Returns alert dict or None for the latest day."""
    if len(rows) < lookback + 2:
        return None
    last, prev = rows[-1], rows[-2]
    base = [r["v"] for r in rows[-(lookback + 1):-1]]
    avg = mean(base) if base else 0
    out = []
    chg = (last["c"] / prev["c"] - 1) * 100
    mult = last["v"] / avg if avg else 0
    if mult >= vol_mult:
        out.append(f"volume {mult:.1f}x {lookback}d avg")
    if abs(chg) >= price_pct:
        out.append(f"{chg:+.1f}% on the day")
    if not out:
        return None
    return {"date": last["d"], "chg": round(chg, 2), "vol_mult": round(mult, 2), "reasons": out}
