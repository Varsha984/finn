"""Pull side: promised-vs-delivered from concall transcripts (primary sources only).

Pipeline (cost-aware):
  1. screener_docs(ticker) -> last 4 transcript PDFs                (free, cached)
  2. chunk each transcript, keep chunks containing forward-looking numbers (regex) (free)
  3. cheap model (Haiku-class) extracts {metric, target, period, quote, page}      (bulk, cheap)
  4. cheap model extracts delivered actuals from the NEXT transcripts' opening remarks
  5. strong model only for the final verdict/tone synthesis, over ~1k tokens of structured claims
Every claim carries a verbatim quote + doc label, and the prompt forbids outside knowledge.

Usage:  set ONE of GEMINI_API_KEY / GROQ_API_KEY (free), or run Ollama locally (no key),
        then: python -m finn.pull TICKER
"""
import hashlib, json, os, re, sys, time, urllib.request, urllib.error
from . import sources


def _load_env(path=".env"):
    """Tiny .env reader (no dependency). Real environment variables win over the file."""
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8-sig"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

PROVIDER = os.getenv("FINN_PROVIDER") or (
    "gemini" if os.getenv("GEMINI_API_KEY") else "groq" if os.getenv("GROQ_API_KEY")
    else "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "ollama")
MODELS = {  # (cheap, strong). Model names change; override with FINN_CHEAP_MODEL / FINN_STRONG_MODEL.
    "gemini": ("gemini-2.5-flash", "gemini-2.5-flash"),
    "groq": ("openai/gpt-oss-20b", "openai/gpt-oss-120b"),
    "ollama": ("llama3.1", "llama3.1"),
    "anthropic": ("claude-haiku-4-5", "claude-sonnet-4-5"),
}
CHEAP = os.getenv("FINN_CHEAP_MODEL", MODELS[PROVIDER][0])
STRONG = os.getenv("FINN_STRONG_MODEL", MODELS[PROVIDER][1])
FORWARD = re.compile(r"(guid|expect|target|aim|going to|will be|confident|outlook).{0,80}(\d+\s?%|\d+\s?(bps|crore|cr|bn|billion))", re.I | re.S)

SYSTEM = ("You are an analyst. Use ONLY the provided transcript excerpts. Do not use outside knowledge, "
          "news or broker views. Every item must include a verbatim quote (<=25 words). "
          "If the excerpts do not say it, return an empty list. Output JSON only.")


def _post(url, body, headers=None, retries=5):
    """POST JSON. Retries on 429/5xx (free tiers rate-limit), honouring Retry-After."""
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", "user-agent": "finn/0.1", **(headers or {})})
    for i in range(retries):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i < retries - 1:
                wait = float(e.headers.get("retry-after") or 2 ** (i + 1))
                print(f"  rate limited ({e.code}), waiting {wait:.0f}s...", file=sys.stderr)
                time.sleep(min(wait, 60)); continue
            raise RuntimeError(f"{e.code} from {url.split('?')[0]}: {e.read().decode()[:300]}") from None


def _llm_call(model, user, max_tokens=1500):
    """One function, four providers. Returns the model's text."""
    if PROVIDER == "gemini":
        r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={os.environ['GEMINI_API_KEY']}",
                  {"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": [{"parts": [{"text": user}]}],
                   "generationConfig": {"maxOutputTokens": max_tokens, "responseMimeType": "application/json"}})
        return r["candidates"][0]["content"]["parts"][0]["text"]
    if PROVIDER == "groq":
        body = {"model": model, "max_tokens": max_tokens,  # Groq counts the requested size against your per-minute quota: keep it small
                "temperature": 0, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
        hdr = {"authorization": "Bearer " + os.environ["GROQ_API_KEY"]}
        url = "https://api.groq.com/openai/v1/chat/completions"
        if "gpt-oss" in model:
            body["reasoning_effort"] = "low"  # fewer hidden thinking tokens -> fewer empty/cut-off replies
        try:
            r = _post(url, body, hdr)
        except RuntimeError as e:
            if "400" not in str(e):
                raise
            body.pop("response_format", None)  # model may not support these options; prompt still asks for JSON
            body.pop("reasoning_effort", None)
            r = _post(url, body, hdr)
        time.sleep(float(os.getenv("FINN_PAUSE", "5")))  # stay under free-tier requests/min
        return r["choices"][0]["message"]["content"]
    if PROVIDER == "ollama":
        r = _post("http://localhost:11434/api/chat", {"model": model, "stream": False, "format": "json",
                  "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]})
        return r["message"]["content"]
    r = _post("https://api.anthropic.com/v1/messages", {"model": model, "max_tokens": max_tokens, "system": SYSTEM,
              "messages": [{"role": "user", "content": user}]},
              {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    return r["content"][0]["text"]


LLM_CACHE = os.path.join("data", "cache", "llm")


def llm(model, user, max_tokens=1500):
    """Cached: identical (provider, model, prompt) is never paid for or waited on twice. Reruns resume instantly."""
    key = hashlib.md5(f"{PROVIDER}|{model}|{user}".encode()).hexdigest()
    path = os.path.join(LLM_CACHE, key + ".txt")
    if os.path.exists(path):
        return open(path, encoding="utf-8").read()
    out = _llm_call(model, user, max_tokens)
    if out and out.strip():  # never cache an empty reply
        os.makedirs(LLM_CACHE, exist_ok=True)
        open(path, "w", encoding="utf-8").write(out)
    return out


def parse_json(text):
    """Models sometimes wrap JSON in code fences or an object; always return a list."""
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        m = re.search(r"[\[{].*[\]}]", text, re.S)  # JSON buried in chatter
        try:
            data = json.loads(m.group(0)) if m else []
        except ValueError:
            print(f"[finn] unreadable model reply skipped: {text[:120]!r}", file=sys.stderr)
            return []
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), [data])
    return data


QTR = re.compile(r"\bQ\s?([1-4])\s*(?:FY|F\.Y\.?)?\s*['’-]?\s*(?:20)?(\d{2})\b", re.I)


def label_of(pages, fallback, i):
    """Name a transcript by the quarter mentioned on its first pages, e.g. 'Q2 FY26'."""
    m = QTR.search(" ".join(pages[:2]))
    return f"Q{m.group(1)} FY{m.group(2)}" if m else f"{fallback} #{i + 1}"


def chunks(pages, size=3000):
    text = "\n".join(f"[p{i+1}] {t}" for i, t in enumerate(pages))
    return [text[i:i + size] for i in range(0, len(text), size)]


def forward_chunks(pages):
    return [c for c in chunks(pages) if FORWARD.search(c)][:4]  # cap spend per call


ACTUAL = re.compile(r"(margin|growth|revenue|headcount|attrition|TCV|order book|capex|utili[sz]ation).{0,100}"
                    r"(was|were|stood|reported|grew|came in|delivered|achieved|ended|at)\b.{0,60}\d+(\.\d+)?\s?(%|bps|crore|billion|mn|bn)", re.I | re.S)


def actual_chunks(pages):
    return [c for c in chunks(pages) if ACTUAL.search(c)][:2]


def order_key(label, idx):
    """Oldest first. Parse 'Q2 FY26'; otherwise assume screener lists newest first and reverse."""
    m = re.match(r"Q(\d) FY(\d\d)", label)
    return (int(m.group(2)), int(m.group(1))) if m else (0, -idx)


def promised_vs_delivered(ticker):
    docs = sources.screener_docs(ticker)["transcripts"][:4]
    print(f"[finn] transcripts found: {len(docs)}", file=sys.stderr)
    claims, actuals = [], []
    for i, d in enumerate(docs):
        pages = sources.pdf_text(d["url"])
        d["label"] = label_of(pages, d["label"], i)
        d["idx"] = i
        fc, ac = forward_chunks(pages), actual_chunks(pages)
        print(f"[finn] {d['label']}: {len(pages)} pages, {len(fc)} guidance chunks, {len(ac)} results chunks", file=sys.stderr)
        for c in fc:
            try:
                out = llm(CHEAP, 'Extract explicit forward guidance (growth, margin, capex). Return a JSON object '
                                 '{"items":[{"metric","target","period","quote","page"}]} from:\n' + c, 1200)
                for item in parse_json(out):
                    item["call"] = d["label"]; claims.append(item)
            except Exception as e:
                print(f"[finn] chunk skipped: {e}", file=sys.stderr)
        for c in ac:
            try:
                out = llm(CHEAP, 'Extract numbers management reports as ALREADY ACHIEVED (not future targets). Return a JSON object '
                                 '{"items":[{"metric","value","period","quote","page"}]} from:\n' + c, 1200)
                for item in parse_json(out):
                    item["call"] = d["label"]; actuals.append(item)
            except Exception as e:
                print(f"[finn] chunk skipped: {e}", file=sys.stderr)
    print(f"[finn] guidance claims: {len(claims)}, reported results: {len(actuals)}", file=sys.stderr)
    if not claims:  # never ask the model to synthesise from nothing: it would invent rows
        return []
    order = {d["label"]: order_key(d["label"], d["idx"]) for d in docs}
    claims.sort(key=lambda x: order.get(x["call"], (0, 0))); actuals.sort(key=lambda x: order.get(x["call"], (0, 0)))
    verdict = llm(STRONG, "Calls are listed oldest to newest. For each guidance claim, compare it with the results reported "
                          "on LATER calls. Use only the data given. If no later result covers it, set status to "
                          '"unclear" and delivered to "not reported". Return a JSON object '
                          '{"items":[{"metric","promised","delivered","status","evidence_quote","source"}]} where status is '
                          'one of delivered, missed, revised, unclear and source is the call label.\n'
                          + json.dumps({"guidance": claims, "reported": actuals}), 3000)
    res = parse_json(verdict)
    if not res:
        print(f"[finn] verdict step returned nothing. Raw reply: {verdict[:400]!r}", file=sys.stderr)
    return res


def status_of(x):
    x = str(x).lower()
    return "met" if x.startswith(("deliver", "met", "achiev")) else "rev" if x.startswith(("revis", "partial", "mixed")) else "unc" if x.startswith(("unclear", "unknown", "n/a")) else "miss"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python -m finn.pull TICKER   (e.g. TCS)")
    if PROVIDER == "ollama" and not os.getenv("FINN_PROVIDER"):
        sys.exit("No API key found. Put GROQ_API_KEY=gsk_... in a file named .env in the folder you run this from "
                 f"(currently: {os.getcwd()}), or set it in the terminal.")
    print(f"[finn] provider={PROVIDER}, models={CHEAP} / {STRONG}", file=sys.stderr)
    t = sys.argv[1].upper()
    res = promised_vs_delivered(t)
    if not res:
        sys.exit(f"No guidance found for {t}: nothing saved. Check the counts above (0 transcripts = screener.in fetch failed).")
    # map to the UI's row shape and save so build.py picks it up
    rows = [{"metric": r.get("metric", ""), "said": r.get("promised", ""), "call": r.get("source", ""),
             "got": r.get("delivered", ""), "status": status_of(r.get("status", "")),
             "quote": r.get("evidence_quote", "")} for r in res]
    os.makedirs("data/pvd", exist_ok=True)
    json.dump(rows, open(f"data/pvd/{t}.json", "w"), indent=2)
    print(f"saved data/pvd/{t}.json - now run: python build.py")
