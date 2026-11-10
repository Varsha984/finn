# FINN: a filter-first investing agent (mobile-first prototype)

**Opinion:** an investor's problem is triage, not aggregation. FINN reads for you and shows only what needs a decision.

Open `index.html` on a phone (or the GitHub Pages link). No backend is needed to view it.

## What is real and what is sample (please read)

| Part | Status |
|---|---|
| **Ask tab, promised vs delivered** | **Real.** Run end to end on TCS concall transcripts fetched from screener.in, extracted with free Groq models. Every quote is machine-checked against the transcript text (green "verified" / red "not found"). |
| Today (digest) and Alerts | The logic is real (rules classifier, 0-100 priority, configurable thresholds). The **data is SAMPLE**: seeded synthetic prices and invented filings, labelled with a "SAMPLE DATA" badge. |
| Results card (Revenue / EBITDA / PBT / PAT, QoQ, YoY) | UI and maths are real and tested; the numbers shown are sample. Parsing a real results PDF is not built. |
| Management-change bio | Fixture. No LinkedIn lookup. |
| Live prices (yfinance) and live NSE filings | Code is written (`finn/sources.py`, `python run.py --live`) but **not verified**; falls back to sample data on any failure. |
| Research views | 1 of the 8 suggested (promised vs delivered). |

## How it works
- `finn/classify.py`: rules map exchange subjects to categories, then score 0-100 and tier into *needs you* / *worth a skim* / *routine (collapsed)*. An LLM would only be used for low-confidence items.
- `finn/alerts.py`: volume multiple vs 20-day average and ±% price move, user-configurable; mirrored in the page's JavaScript so sliders update live.
- `finn/pull.py`: screener.in transcripts -> PDF text -> regex keeps only guidance-like and results-like chunks -> small model (`gpt-oss-20b`) extracts claims and reported results -> larger model (`gpt-oss-120b`) compares promises with later calls -> each quote verified against the transcripts. Long-term targets are marked "unclear", not "missed", and dropped claims come back as "unclear" rows.
- Primary sources only (transcripts). The prompts forbid outside knowledge.

## Cost choices
Regex pre-filtering before any model call, small model for bulk extraction and one bigger call for the verdict, every model reply cached on disk (reruns are free and instant), PDFs and fetches cached, free-tier models only. The provider layer works with Groq, Gemini, Ollama (local) or Claude.

## Run it
```
python -m venv .venv
.venv\Scripts\Activate.ps1        # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests
python run.py                      # sample data, serves http://localhost:8000/index.html
```
Real research on any NSE ticker (needs internet and one free key in a `.env` file, see `.env.example`):
```
GROQ_API_KEY=gsk_your_key          # or GEMINI_API_KEY, or run Ollama with no key
python -m finn.pull INFY
python build.py
```
Free-tier limits are strict, so calls are paced (`FINN_PAUSE`, default 5s) and 429s retry automatically.

## Known limits
Free small models can misjudge a verdict even when the quote is genuine, so verification proves the quote is real, not that the conclusion is right. Transcript order and quarter labels are inferred from the PDF text. Selectors for screener.in and NSE may break when those sites change.

## Next
Wire live NSE filings and results-PDF parsing into the digest, LinkedIn enrichment for management changes, the other research views, and push notifications.
