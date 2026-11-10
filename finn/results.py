"""Quarterly results: headline numbers + QoQ / YoY deltas.

Extraction is two-stage: regex over the filing's financial-results table for the common
'Total income / Profit before tax / Net profit' rows (free), LLM fallback only if that fails.
EBITDA is derived (PBT + finance cost + depreciation - other income) because filings don't report it.
"""
import re

def pct(cur, base):
    return None if not base else round((cur / base - 1) * 100, 1)


def headline(cur, qoq, yoy):
    """cur/qoq/yoy: dicts with revenue, ebitda, pbt, pat (Rs crore)."""
    out = {}
    for k in ("revenue", "ebitda", "pbt", "pat"):
        out[k] = {"value": cur[k], "qoq": pct(cur[k], qoq[k]), "yoy": pct(cur[k], yoy[k])}
    out["ebitda_margin"] = round(cur["ebitda"] / cur["revenue"] * 100, 1)
    out["margin_delta_yoy_bps"] = round((cur["ebitda"] / cur["revenue"] - yoy["ebitda"] / yoy["revenue"]) * 10000)
    return out


def derive_ebitda(pbt, finance_cost, depreciation, other_income):
    return pbt + finance_cost + depreciation - other_income


ROW = re.compile(r"(total income|revenue from operations|profit before tax|net profit|profit for the (?:period|quarter))[^\d\-]{0,40}(-?[\d,]+\.?\d*)", re.I)

def scan_table(text):
    found = {}
    for label, num in ROW.findall(text):
        found.setdefault(label.lower(), float(num.replace(",", "")))
    return found
