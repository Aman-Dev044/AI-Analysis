"""Deterministic facts pulled straight from document text (no model involved).

Everything here is source-grounded: dates, amounts, contacts, document type,
reading stats and expiry status are computed from the text itself so they can
be trusted even when the language model is small or unavailable.
"""

import re
from datetime import date, datetime
from typing import Optional

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
DATE_RE = re.compile(
    rf"\b(?:"
    rf"(?P<dmy>\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\.?,?\s+\d{{4}})"
    rf"|(?P<mdy>(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}})"
    rf"|(?P<iso>\d{{4}}-\d{{1,2}}-\d{{1,2}})"
    rf"|(?P<num>\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{4}})"
    rf")\b",
    re.IGNORECASE,
)
LABELS = [
    ("expiry", re.compile(r"\b(expir\w*|valid\s+(?:until|till|upto|up\s+to|through|thru)|validity|renew\w*|date\s+of\s+expiry)\b", re.I)),
    ("deadline", re.compile(r"\b(deadline|due(?:\s+date)?|last\s+date|submit\w*\s+by|on\s+or\s+before|before)\b", re.I)),
    ("review", re.compile(r"\b(review|meeting|appointment|hearing|interview|exam\w*)\b", re.I)),
    ("issue", re.compile(r"\b(issue[d]?|date\s+of\s+issue|dated|effective|start\w*|commenc\w*)\b", re.I)),
    ("birth", re.compile(r"\b(date\s+of\s+birth|dob|born)\b", re.I)),
]
AMOUNT_RE = re.compile(
    r"(?:(?:₹|Rs\.?|INR|USD|US\$|\$|€|EUR|£|GBP)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:lakh|lakhs|crore|crores|k|m|bn|million|billion))?"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:lakh|lakhs|crore|crores|rupees|dollars|INR|USD)\b)",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<![\w/.-])(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)?\d{3,5}[\s-]?\d{4,5}(?![\w/.-])")
URL_RE = re.compile(r"\bhttps?://[^\s<>()\"']+", re.I)
PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")

DOC_TYPES = [
    ("Work plan / schedule", r"(?m)^Period:|\bquarterly review\b|\bwork schedule\b|\bweekly plan\b"),
    ("Invoice", r"\binvoice\b|\bGSTIN\b|\btax invoice\b|\bbill to\b"),
    ("Receipt", r"\breceipt\b|\bpayment received\b|\btransaction id\b"),
    ("Bank statement", r"\baccount statement\b|\bopening balance\b|\bclosing balance\b"),
    ("Resume / CV", r"\bcurriculum vitae\b|\bresume\b|\bwork experience\b.*\beducation\b"),
    ("Contract / Agreement", r"\bagreement\b|\bcontract\b|\bhereinafter\b|\bparty of the first part\b"),
    ("Insurance policy", r"\bpolicy\s*(?:no|number)\b|\bsum insured\b|\bpremium\b|\binsured\b"),
    ("Driving licence", r"\bdriving licen[cs]e\b"),
    ("Passport", r"\bpassport\b"),
    ("PAN card", r"\bpermanent account number\b|\bincome tax department\b"),
    ("Aadhaar card", r"\baadhaa?r\b|\bunique identification\b"),
    ("Marksheet / Result", r"\bmarksheet\b|\bmark\s+sheet\b|\bgrade card\b|\bcgpa\b|\bsgpa\b"),
    ("Certificate", r"\bcertificate\b|\bthis is to certify\b"),
    ("Legal notice", r"\blegal notice\b|\bhon'?ble court\b|\bpetitioner\b|\brespondent\b"),
    ("Research paper", r"\babstract\b.*\b(introduction|methodology|references)\b"),
    ("Meeting notes", r"\bminutes of (?:the )?meeting\b|\bagenda\b|\battendees\b"),
    ("Report", r"\breport\b|\bexecutive summary\b|\bfindings\b"),
    ("Letter", r"^\s*(?:dear|respected)\b|\byours (?:sincerely|faithfully)\b"),
]


def _strip_ordinal(value: str) -> str:
    return re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value, flags=re.I).replace(".", " ").replace(",", " ")


def parse_date(raw: str) -> tuple[Optional[date], bool]:
    """Return (date, ambiguous). Numeric dd/mm vs mm/dd defaults to day-first."""
    value = raw.strip()
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", value):
        try:
            return date.fromisoformat("-".join(p.zfill(2) for p in value.split("-"))), False
        except ValueError:
            return None, False
    num = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", value)
    if num:
        a, b, y = (int(x) for x in num.groups())
        ambiguous = a <= 12 and b <= 12 and a != b
        day, month = (b, a) if a <= 12 < b else (a, b)
        try:
            return date(y, month, day), ambiguous
        except ValueError:
            return None, False
    cleaned = " ".join(_strip_ordinal(value).split())
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(cleaned.replace("Sept ", "Sep "), fmt).date(), False
        except ValueError:
            continue
    return None, False


def _context(text: str, start: int, end: int, width: int = 90) -> str:
    left = text.rfind("\n", 0, start)
    left = max(left + 1, start - width)
    right = text.find("\n", end)
    right = min(right if right != -1 else len(text), end + width)
    snippet = " ".join(text[left:right].split())
    return ("…" if left > 0 and text[left - 1] != "\n" else "") + snippet


def _label_for(text: str, start: int) -> str:
    window = text[max(0, start - 60):start]
    best, best_pos = "mentioned", -1
    for name, pattern in LABELS:
        for match in pattern.finditer(window):
            if match.start() > best_pos:
                best, best_pos = name, match.start()
    return best


def extract_dates(text: str, today: Optional[date] = None, limit: int = 80) -> list[dict]:
    today = today or date.today()
    seen, out = set(), []
    for match in DATE_RE.finditer(text):
        raw = match.group(0)
        parsed, ambiguous = parse_date(raw)
        if parsed is None or not (1900 <= parsed.year <= 2200):
            continue
        label = _label_for(text, match.start())
        key = (parsed, label)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "text": raw,
            "iso": parsed.isoformat(),
            "label": label,
            "ambiguous": ambiguous,
            "days_from_today": (parsed - today).days,
            "context": _context(text, match.start(), match.end()),
        })
        if len(out) >= limit:
            break
    out.sort(key=lambda d: d["iso"])
    return out


def expiry_info(dates: list[dict], soon_days: int = 30) -> Optional[dict]:
    """The document's own expiry/validity date, if one is explicitly labelled."""
    candidates = [d for d in dates if d["label"] == "expiry"]
    if not candidates:
        return None
    chosen = max(candidates, key=lambda d: d["iso"])
    days = chosen["days_from_today"]
    status = "expired" if days < 0 else "expiring_soon" if days <= soon_days else "valid"
    if chosen["ambiguous"]:
        status = "verify"
    return {"date": chosen["iso"], "text": chosen["text"], "days_remaining": days,
            "status": status, "context": chosen["context"]}


def detect_type(text: str) -> str:
    sample = text[:20000]
    for label, pattern in DOC_TYPES:
        if re.search(pattern, sample, re.IGNORECASE | re.DOTALL):
            return label
    return "General document"


def _unique(values, limit=25):
    seen, out = set(), []
    for value in values:
        v = " ".join(value.split()).strip(" .,;:")
        key = v.lower()
        if v and key not in seen:
            seen.add(key)
            out.append(v)
        if len(out) >= limit:
            break
    return out


def headings(text: str, limit: int = 20) -> list[str]:
    found = []
    for line in text.splitlines():
        s = line.strip().strip("-=#* ").strip()
        if not (3 <= len(s) <= 90):
            continue
        letters = [c for c in s if c.isalpha()]
        if line.lstrip().startswith("#") or (letters and sum(c.isupper() for c in letters) / len(letters) > 0.8
                                             and len(s.split()) <= 12):
            found.append(s)
    return _unique(found, limit)


def analyze(text: str, today: Optional[date] = None, soon_days: int = 30) -> dict:
    today = today or date.today()
    words = len(re.findall(r"\w+", text))
    dates = extract_dates(text, today)
    phones = [p for p in PHONE_RE.findall(text) if 10 <= len(re.sub(r"\D", "", p)) <= 13]
    upcoming = [d for d in dates if d["days_from_today"] >= 0 and d["label"] in {"deadline", "expiry", "review"}]
    return {
        "doc_type": detect_type(text),
        "stats": {
            "words": words,
            "characters": len(text),
            "lines": text.count("\n") + 1 if text else 0,
            "reading_minutes": max(1, round(words / 220)) if words else 0,
        },
        "dates": dates,
        "upcoming": upcoming[:10],
        "expiry": expiry_info(dates, soon_days),
        "amounts": _unique(AMOUNT_RE.findall(text)),
        "percentages": _unique(PERCENT_RE.findall(text), 15),
        "emails": _unique(EMAIL_RE.findall(text), 15),
        "phones": _unique(phones, 15),
        "urls": _unique(URL_RE.findall(text), 15),
        "headings": headings(text),
    }


def facts_for_prompt(info: dict, max_dates: int = 25) -> str:
    """Compact list of verified facts handed to the model so it highlights the right values."""
    lines = []
    if info.get("doc_type"):
        lines.append(f"Detected document type: {info['doc_type']}")
    for d in info.get("dates", [])[:max_dates]:
        lines.append(f"Date: {d['text']} ({d['label']}) — {d['context'][:140]}")
    if info.get("amounts"):
        lines.append("Amounts: " + ", ".join(info["amounts"][:15]))
    if info.get("percentages"):
        lines.append("Percentages: " + ", ".join(info["percentages"][:10]))
    return "\n".join(lines)
