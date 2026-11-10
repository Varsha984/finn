"""Announcement classifier + priority score.

Cost design: rules first (free, instant, covers ~85% of NSE subjects because
exchange subjects are formulaic). Only low-confidence items ("unclassified"
with a long body) are worth escalating to a cheap LLM - see escalate().
"""
import re

# (category, regex) - order matters: first match wins.
RULES = [
    ("management_change", r"resign|appoint|cessation|re-?designation|change in (director|management|key managerial)|\b(ceo|cfo|md|cio|coo)\b.*(appoint|resign)"),
    ("results", r"financial results|quarterly results|results for the (quarter|year)|outcome of board meeting.*result|investor presentation.*(q[1-4]|quarter)"),
    ("earnings_call", r"earnings call|concall|conference call|analyst.*call|transcript"),
    ("M&A", r"acqui|merger|amalgamat|demerger|joint venture|stake in|scheme of arrangement|subsidiary"),
    ("fund_raise", r"rights issue|qip|preferential|buy-?back|commercial paper|fund ?rais|ncd|debenture"),
    ("litigation", r"show cause|penalty|fine\b|sebi order|court|tribunal|nclt|insolvency|notice from|litigation"),
    ("credit_rating", r"credit rating|crisil|icra|care ratings|india ratings|rating (upgrade|downgrade|reaffirm)"),
    ("pledging", r"pledge|invocation|encumbrance"),
    ("insider_trading", r"insider|sast|regulation 7\(2\)|disposal of shares by promoter|acquisition of shares by promoter"),
    ("dividend", r"dividend|record date"),
    ("bonus_split", r"bonus|stock split|sub-?division of"),
    ("capex", r"capex|capacity expansion|new plant|greenfield|brownfield|commission(ing)? of"),
    ("postal_ballot", r"postal ballot"),
    ("agm_egm", r"\bagm\b|\begm\b|annual general meeting|extraordinary general"),
    ("investor_meetings", r"analyst.*meet|investor meet|institutional investor|schedule of.*meet"),
    ("press_release", r"press release|order win|bags order|launch|partnership|clarification|awarded"),
]

# Base priority 0-100: how much a time-poor investor should care.
BASE = {
    "results": 90, "management_change": 85, "M&A": 85, "litigation": 80,
    "fund_raise": 75, "pledging": 75, "credit_rating": 65, "capex": 60,
    "dividend": 55, "bonus_split": 55, "insider_trading": 50, "press_release": 45,
    "earnings_call": 40, "investor_meetings": 20, "agm_egm": 15,
    "postal_ballot": 10, "unclassified": 5,
}

NEGATIVE = re.compile(r"resign|downgrade|penalty|fine\b|show cause|insolvency|invocation|default|qualif", re.I)
SENIOR = re.compile(r"\b(ceo|cfo|md|managing director|chairman|coo|cio)\b", re.I)
ROUTINE = re.compile(r"esop|compliance certificate|reg(ulation)? ?74|trading window|newspaper|duplicate share|loss of share|disclosure under regulation 30\(.*\) - routine", re.I)


def classify(subject: str, body: str = "") -> str:
    text = f"{subject} {body}".lower()
    if ROUTINE.search(text):
        return "unclassified"
    for cat, pat in RULES:
        if re.search(pat, text, re.I):
            return cat
    return "unclassified"


def priority(category: str, subject: str = "", body: str = "") -> int:
    p = BASE.get(category, 5)
    text = f"{subject} {body}"
    if category == "management_change" and SENIOR.search(text):
        p += 8  # CEO/CFO exit matters more than a non-exec director
    if NEGATIVE.search(text) and category not in ("unclassified",):
        p += 5  # bad news first
    return min(p, 100)


def tier(p: int) -> str:
    """'must' = push now, 'skim' = digest body, 'routine' = collapsed."""
    return "must" if p >= 70 else "skim" if p >= 35 else "routine"


def escalate(subject: str, body: str) -> bool:
    """True when rules gave up on something that looks substantive -> send to a cheap LLM."""
    return classify(subject, body) == "unclassified" and len(body) > 400 and not ROUTINE.search(subject)
