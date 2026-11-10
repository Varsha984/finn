import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from finn import classify as c, alerts, results


def test_classify():
    assert c.classify("Appointment of Chief Financial Officer") == "management_change"
    assert c.classify("Outcome of Board Meeting - Financial Results for the quarter") == "results"
    assert c.classify("Allotment of equity shares under ESOP") == "unclassified"
    assert c.classify("Promoter pledge invocation disclosure") == "pledging"
    assert c.classify("Credit rating reaffirmed by CRISIL") == "credit_rating"
    assert c.classify("Notice of Postal Ballot") == "postal_ballot"


def test_priority_order():
    assert c.priority("results") > c.priority("dividend") > c.priority("agm_egm")
    assert c.priority("management_change", "Resignation of CFO") > c.priority("management_change", "Appointment of Director")
    assert c.tier(c.priority("unclassified")) == "routine"


def test_alerts():
    rows = [{"d": str(i), "c": 100, "v": 1000} for i in range(25)]
    assert alerts.unusual(rows) is None
    rows[-1] = {"d": "x", "c": 94, "v": 3000}
    a = alerts.unusual(rows, 2.0, 4.0)
    assert a and len(a["reasons"]) == 2
    assert alerts.unusual(rows, 4.0, 10.0) is None


def test_results():
    h = results.headline({"revenue": 110, "ebitda": 22, "pbt": 18, "pat": 13}, {"revenue": 100, "ebitda": 20, "pbt": 16, "pat": 12}, {"revenue": 100, "ebitda": 20, "pbt": 16, "pat": 12})
    assert h["revenue"]["qoq"] == 10.0 and h["ebitda_margin"] == 20.0 and h["margin_delta_yoy_bps"] == 0
    assert results.derive_ebitda(100, 10, 20, 5) == 125


def test_parse_json():
    from finn.pull import parse_json
    assert parse_json('```json\n[{"a":1}]\n```') == [{"a": 1}]
    assert parse_json('{"items":[{"a":1}]}') == [{"a": 1}]


def test_groq_path(monkeypatch):
    """Fake Groq (OpenAI-shaped) responses end to end, incl. a 429 retry."""
    import io, urllib.error, json as _j
    from finn import pull, sources
    monkeypatch.setattr(pull, "PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "k"); monkeypatch.setenv("FINN_PAUSE", "0")
    monkeypatch.setattr(pull.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class R:
        def __init__(s, d): s.d = d
        def read(s): return _j.dumps(s.d).encode()

    def fake_open(req, timeout=0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "x", {"retry-after": "1"}, io.BytesIO(b"{}"))
        body = _j.loads(req.data)
        assert body["response_format"] == {"type": "json_object"}
        assert req.full_url.startswith("https://api.groq.com/openai/v1/")
        user = body["messages"][1]["content"]
        item = {"metric": "margin", "target": "26%", "period": "FY26", "quote": "q", "page": 1}
        out = {"items": [item]} if "Extract" in user else {"items": [{"metric": "margin", "promised": "26%", "delivered": "24%", "status": "missed", "evidence_quote": "q", "source": "s"}]}
        return R({"choices": [{"message": {"content": _j.dumps(out)}}]})

    monkeypatch.setattr(pull.urllib.request, "urlopen", fake_open)
    monkeypatch.setattr(sources, "screener_docs", lambda t: {"transcripts": [{"label": "Q1", "url": "u"}]})
    monkeypatch.setattr(sources, "pdf_text", lambda u: ["Management expects operating margin target of 26% going to be achieved. " * 5])
    res = pull.promised_vs_delivered("TCS")
    assert res[0]["status"] == "missed" and calls["n"] >= 3
