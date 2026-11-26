"""Deterministic facts pulled straight from document text (no model involved).

Everything here is source-grounded: dates, amounts, contacts, document type,
reading stats and expiry status are computed from the text itself so they can
be trusted even when the language model is small or unavailable.
"""

import bisect
import re
from collections import Counter
from datetime import date
from typing import Optional

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
# Without a year, a lowercase "may" is usually the verb ("Step 1 may take"), so only "May" / "MAY" count.
_MONTHS_NO_YEAR = MONTHS.replace("May|", "") + "|(?-i:May|MAY)"
WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tues|Tue|Wed|Thurs|Thur|Thu|Fri|Sat|Sun"
_WD = rf"(?:(?:{WEEKDAYS})\.?,?\s+)?"
_ORD = r"(?:st|nd|rd|th)?"
DATE_RE = re.compile(
    rf"\b(?:"
    rf"(?P<dmy>{_WD}\d{{1,2}}{_ORD}\s+(?:of\s+)?(?:{MONTHS})\.?,?\s+\d{{4}})"
    rf"|(?P<mdy>{_WD}(?:{MONTHS})\.?\s+\d{{1,2}}{_ORD},?\s+\d{{4}})"
    rf"|(?P<iso>\d{{4}}-\d{{1,2}}-\d{{1,2}})"
    # Forms and policy schedules: "09-NOV-2005", "17-Jul-2021", "10/Jun/2021".
    rf"|(?P<dmyh>\d{{1,2}}[-/](?:{MONTHS})[-/]\d{{4}})"
    rf"|(?P<num>\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{4}})"
    # Schedules and letters often leave the year out: "Sat, 14 Nov", "Nov 14th".
    rf"|(?P<dm>{_WD}\d{{1,2}}{_ORD}\s+(?:of\s+)?(?:{_MONTHS_NO_YEAR})\.?)"
    rf"|(?P<md>{_WD}(?:{_MONTHS_NO_YEAR})\.?\s+\d{{1,2}}{_ORD})"
    rf")\b",
    re.IGNORECASE,
)
_MONTH_NUM = {name.lower(): (i % 12) + 1 for i, name in enumerate(
    "January February March April May June July August September October November December "
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
_MONTH_NUM["sept"] = 9
_WEEKDAY_NUM = {name.lower(): i % 7 for i, name in enumerate(
    "Monday Tuesday Wednesday Thursday Friday Saturday Sunday Mon Tue Wed Thu Fri Sat Sun".split())}
_WEEKDAY_NUM.update({"tues": 1, "thur": 3, "thurs": 3})
_LEAD_WEEKDAY = re.compile(rf"^({WEEKDAYS})\.?,?\s+", re.I)
_TEXT_DMY = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-/]+(?:of\s+)?([A-Za-z]+)\.?,?(?:[\s\-/]+(\d{4}))?", re.I)
_TEXT_MDY = re.compile(r"([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?(?:\s+(\d{4}))?", re.I)
_TIME_PART = r"\d{1,2}(?:[:.]\d{2})?\s*(?:[ap]\.?m\.?)?"
# "10:00–12:00", "9.30 am - 11 am", "3 pm": a time (range) opening a schedule line.
TIME_SPAN_RE = re.compile(
    rf"^(?P<time>\d{{1,2}}[:.]\d{{2}}\s*(?:[ap]\.?m\.?)?(?:\s*(?:-|–|—|to)\s*{_TIME_PART})?"
    rf"|\d{{1,2}}\s*[ap]\.?m\.?(?:\s*(?:-|–|—|to)\s*{_TIME_PART})?)(?![\w:])\s*[-–—:|]?\s*",
    re.I,
)
LABELS = [
    ("expiry", re.compile(r"\b(expir\w*|valid\s+(?:until|till|upto|up\s+to|through|thru)|validity|renew\w*|date\s+of\s+expiry)\b", re.I)),
    ("deadline", re.compile(r"\b(deadline|due(?:\s+date)?|last\s+date|submit\w*\s+by|on\s+or\s+before|before)\b|\bby\s*$", re.I)),
    ("review", re.compile(r"\b(review|meeting|appointment|hearing|interview|exam\w*)\b", re.I)),
    ("issue", re.compile(r"\b(issued|issue\s+date|date\s+of\s+issue|dated|effective|start\w*|commenc\w*)\b", re.I)),
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
    # A word like "invoice" or "passport" in passing ("Rahul will send the invoice") does not make the type.
    # A policy schedule is often also a tax invoice: the policy is what the document is about.
    ("Insurance policy", r"\bpolicy\s*schedule\b|\bcertificate\s*of\s*insurance\b|\bpolicy\s*no\b.*\bpremium\b"),
    ("Invoice", r"\binvoice\s*(?:no|number|#|date)\b|(?:^|\n)[ \t]*(?:tax[ \t]+)?invoice[ \t]*(?:\n|$)|\bGSTIN\b|\btax invoice\b|\bbill to\b"),
    ("Receipt", r"\breceipt\b|\bpayment received\b|\btransaction id\b"),
    ("Bank statement", r"\baccount statement\b|\bopening balance\b|\bclosing balance\b"),
    ("Resume / CV", r"\bcurriculum vitae\b|\bresume\b|\bwork experience\b.*\beducation\b"),
    ("Meeting notes", r"\bminutes of (?:the )?[\w ]{0,40}meeting\b|\bagenda\b|\battendees\b"),
    ("Contract / Agreement", r"\bthis (?:agreement|contract)\b|\b(?:agreement|contract) (?:is )?made\b|\bentered into\b"
                             r"|\bhereinafter\b|\bparty of the first part\b|\bterms and conditions\b"
                             r"|^\W*[^\n]{0,60}\b(?:agreement|contract)\W*(?:\n|$)"),
    ("Insurance policy", r"\bpolicy\s*(?:no|number)\b|\bsum insured\b|\bpremium\b|\binsured\b"),
    ("Driving licence", r"\bdriving licen[cs]e\b"),
    ("Visa application", r"\bvisa application\b"),
    # The machine-readable zone starts "P<IND…" on a passport and "V<IND…" / "VTIND…" on a visa.
    ("Visa", r"\bvisa\s*type\b|\bno\.?\s*of\s*entries\b|(?:^|\n)(?-i:V[A-Z<][A-Z]{3}[A-Z]*<<)"),
    ("Passport", r"\bpassport\s*(?:no|number)\b|\bpassport\b.*\bnationality\b|\bnationality\b.*\bpassport\b"
                 r"|(?:^|\n)(?-i:P<[A-Z]{3})"),
    ("Voter ID", r"\belection\s*commission|\belector(?:'s)?\s*photo\b|\bEPIC\b"),
    ("PAN card", r"\bpermanent account number\b|\bincome tax department\b"),
    ("Aadhaar card", r"\baadhaa?r\b|\bunique identification\b|आधार|\bVID\s*:"
                     r"|government of india.*\b[2-9]\d{3} \d{4} \d{4}\b"),
    ("Marksheet / Result", r"\bmarksheet\b|\bmark\s+sheet\b|\bgrade card\b|\bcgpa\b|\bsgpa\b"),
    ("Certificate", r"\bcertificate\b|\bthis is to certify\b"),
    ("Legal notice", r"\blegal notice\b|\bhon'?ble court\b|\bpetitioner\b|\brespondent\b"),
    ("Research paper", r"\babstract\b.*\b(introduction|methodology|references)\b"),
    ("Report", r"\breport\b|\bexecutive summary\b|\bfindings\b"),
    ("Letter", r"^\s*(?:dear|respected)\b|\byours (?:sincerely|faithfully)\b"),
]


def _strip_ordinal(value: str) -> str:
    return re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value, flags=re.I).replace(".", " ").replace(",", " ")


def _pick_year(month: int, day: int, weekday: Optional[int], year: Optional[int],
               today: Optional[date]) -> tuple[Optional[date], bool]:
    """A date written without its year. The year comes from the document (`year`) or, failing that, is the one
    closest to today. A stated weekday ("Sat, 14 Nov") confirms the year; a guess without one is ambiguous."""
    ref = today or date.today()
    base = year or ref.year
    candidates = []
    for y in (base, base + 1, base - 1):
        try:
            candidates.append(date(y, month, day))
        except ValueError:
            continue
    if not candidates:
        return None, False
    if weekday is not None:
        match = next((c for c in candidates if c.weekday() == weekday), None)
        if match:
            return match, False
        return candidates[0], True
    if year:
        return candidates[0], False
    return min(candidates, key=lambda c: abs((c - ref).days)), True


def _text_date(value: str, year: Optional[int], today: Optional[date]) -> tuple[Optional[date], bool]:
    weekday = None
    lead = _LEAD_WEEKDAY.match(value)
    if lead:
        weekday = _WEEKDAY_NUM.get(lead.group(1).lower())
        value = value[lead.end():]
    value = " ".join(value.split())
    m = _TEXT_DMY.fullmatch(value)
    if m:
        day, name, yr = m.group(1), m.group(2), m.group(3)
    else:
        m = _TEXT_MDY.fullmatch(value)
        if not m:
            return None, False
        name, day, yr = m.group(1), m.group(2), m.group(3)
    month = _MONTH_NUM.get(name.lower())
    if not month:
        return None, False
    if yr:
        try:
            parsed = date(int(yr), month, int(day))
        except ValueError:
            return None, False
        # A weekday that disagrees with the date points to a typo somewhere: let the reader check it.
        return parsed, weekday is not None and parsed.weekday() != weekday
    return _pick_year(month, int(day), weekday, year, today)


def parse_date(raw: str, year: Optional[int] = None, today: Optional[date] = None) -> tuple[Optional[date], bool]:
    """Return (date, ambiguous). Numeric dd/mm vs mm/dd defaults to day-first. A date without a year takes
    `year` (the document's own year) or the nearest one to `today`."""
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
    return _text_date(value, year, today)


# Searches below are bounded: on text without line breaks an unbounded rfind per date is quadratic.
def _context(text: str, start: int, end: int, width: int = 90) -> str:
    left = text.rfind("\n", max(0, start - width), start)
    left = max(left + 1, start - width, 0)
    right = text.find("\n", end, end + width)
    right = min(right if right != -1 else len(text), end + width)
    snippet = " ".join(text[left:right].split())
    return ("…" if left > 0 and text[left - 1] != "\n" else "") + snippet


def _event_context(text: str, start: int, end: int, limit: int = 1000) -> str:
    """Keep the full source row for structured schedules, including trailing priority fields."""
    left = text.rfind("\n", max(0, start - limit), start) + 1 or max(0, start - limit)
    right = text.find("\n", end, end + limit)
    if right == -1:
        right = min(len(text), end + limit)
    return " ".join(text[left:right].split())[:limit]


def _label_for(text: str, start: int) -> str:
    """The label words just before a date, on its own line. A date that opens its line may take the label
    from a short line above it ("Valid till" / "20/10/2026" in OCR output), never from unrelated text."""
    line_start = text.rfind("\n", max(0, start - 60), start) + 1
    window = text[max(line_start, start - 60):start]
    if line_start and not window.strip(" \t:-–|•*"):
        above_start = text.rfind("\n", max(0, line_start - 80), line_start - 1) + 1
        above = text[above_start:line_start - 1]
        label_text = above.rstrip(" \t\r:.-–|")
        ends_with_label = any(m.end() >= len(label_text) for _, p in LABELS for m in p.finditer(label_text))
        whole_line = above_start or line_start - 1 < 80
        window = above if whole_line and len(above.split()) <= 6 and ends_with_label else ""
    best, best_pos = "mentioned", -1
    for name, pattern in LABELS:
        for match in pattern.finditer(window):
            if match.start() > best_pos:
                best, best_pos = name, match.start()
    return best


_YEARLESS = ("dm", "md")
_TRAILING_WEEKDAY = re.compile(rf"\s*[,(\-–]?\s*({WEEKDAYS})\b\.?\)?", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_LINE_PUNCT = " \t|,;:-–—•*·()[]"
MAX_ITEMS = 12


class _Lines:
    """Line lookup by character offset (bisect over newline positions, so it stays linear on big texts)."""

    def __init__(self, text: str):
        self.text = text
        self.starts = [0] + [m.end() for m in re.finditer(r"\n", text)]

    def index(self, pos: int) -> int:
        return bisect.bisect_right(self.starts, pos) - 1

    def line(self, i: int) -> str:
        end = self.starts[i + 1] - 1 if i + 1 < len(self.starts) else len(self.text)
        return self.text[self.starts[i]:end]

    def __len__(self):
        return len(self.starts)


def _document_year(matches: list, today: Optional[date] = None) -> Optional[int]:
    """The year the document is about: the most common year among its fully written dates, or among dates
    whose weekday pins the year ("Monday 16 November" can only be one year near today)."""
    years = Counter()
    for m in matches:
        yearless = any(m.group(g) for g in _YEARLESS)
        if yearless and not _LEAD_WEEKDAY.match(m.group(0)):
            continue
        parsed, ambiguous = parse_date(m.group(0), today=today)
        if parsed and not ambiguous and 1900 <= parsed.year <= 2200:
            years[parsed.year] += 1
    return years.most_common(1)[0][0] if years else None


def _year_hint(matches: list, i: int, doc_year: Optional[int], text: str) -> tuple[Optional[int], Optional[date]]:
    """For "14 November – 27 November 2026" the first date takes the year of the second one."""
    m = matches[i]
    for nxt in matches[i + 1:i + 3]:
        between = text[m.end():nxt.start()]
        if "\n" in between or len(between) > 25:
            break
        if not any(nxt.group(g) for g in _YEARLESS):
            end = parse_date(nxt.group(0))[0]
            if end:
                return end.year, end
    return doc_year, None


def _is_date_only(line: str, spans: list[tuple[int, int]], line_start: int) -> bool:
    """True when a line is just its date(s), maybe with a weekday or separators ("Sat, 14 Nov")."""
    if len(spans) > 3 or len(line) > 120:  # a heading holds a date or a range, never a paragraph of them
        return False
    rest = line
    for s, e in sorted(spans, reverse=True):
        rest = rest[:s - line_start] + " " + rest[e - line_start:]
    words = [w for w in re.findall(r"[^\W\d_]{2,}", rest)]
    return len(words) <= 1 and len(rest.strip(_LINE_PUNCT)) <= 12


def _sentence_with(line: str, start: int, end: int) -> str:
    """The sentence of `line` holding [start, end): what the date is about in prose. Only a window around the
    date is searched, so a page-long line with many dates stays linear."""
    lo, hi = max(0, start - 400), min(len(line), end + 400)
    left = max((m.end() for m in _SENTENCE_END.finditer(line, lo, start)), default=lo)
    after = _SENTENCE_END.search(line, end, hi)
    line = line[left:after.start() if after else hi]
    line = " ".join(line.split()).strip(_LINE_PUNCT.replace("(", "").replace(")", ""))
    return line if len(line) <= 220 else line[:219].rstrip() + "…"


_INLINE_TIME = re.compile(
    rf"(?:\s*(?:at|@|from)\s+)?\b(?P<time>\d{{1,2}}[:.]\d{{2}}\s*(?:[ap]\.?m\.?)?(?:\s*(?:-|–|—|to)\s*{_TIME_PART})?"
    rf"|\d{{1,2}}\s*[ap]\.?m\.?(?:\s*(?:-|–|—|to)\s*{_TIME_PART})?)(?![\w:])",
    re.I,
)


def _entry(time: str, what: str) -> dict:
    """One schedule entry; a time written inside the text ("standup 9:30", "dentist 11 am") moves to `time`."""
    what = what.strip(_LINE_PUNCT)
    if not time:
        m = _INLINE_TIME.search(what)
        if m and DATE_RE.search(what[max(0, m.start() - 8):m.end()]) is None:
            time = m.group("time")
            what = (what[:m.start()] + what[m.end():])
            what = re.sub(r"\s+([,;.])", r"\1", " ".join(what.split())).strip(_LINE_PUNCT)
    return {"time": " ".join(time.split()), "what": what[:1].upper() + what[1:]}


def _items_after(lines: _Lines, i: int, heading_lines: set) -> list[dict]:
    """Schedule entries under a date heading: "10:00–12:00" / "Organise room" pairs, or short plain lines."""
    # time_led: entries open with their time ("10:00–12:00" then the activity, or on one line); there, a line
    # without a leading time ends the block. Plain lists ("standup 9:30", "pick up passport") end at a blank line.
    items, pending_time, time_led = [], None, False
    for j in range(i + 1, min(len(lines), i + 40)):
        raw = " ".join(lines.line(j).split())
        if j in heading_lines:
            break
        if not raw:
            if items or pending_time:
                break
            continue
        span = TIME_SPAN_RE.match(raw)
        if span and not raw[span.end():].strip(_LINE_PUNCT):  # a time on its own line: the activity follows
            if pending_time:
                break
            pending_time, time_led = span.group("time"), True
            continue
        if span:  # "10:00–12:00 Organise your room"
            items.append(_entry(span.group("time"), raw[span.end():]))
            pending_time, time_led = None, True
        elif pending_time:
            items.append(_entry(pending_time, raw))
            pending_time = None
        elif time_led or len(raw.split()) > 25:
            break  # untimed text after time-led entries, or a prose paragraph, is no longer this day's plan
        else:
            items.append(_entry("", raw))
        if len(items) >= MAX_ITEMS:
            break
    if items and not time_led:
        items = items[:6]
    return [it for it in items if it["what"]]


def extract_dates(
    text: str,
    today: Optional[date] = None,
    limit: Optional[int] = 80,
    deduplicate: bool = True,
) -> list[dict]:
    """Every date with its label, the text around it and its topic: the sentence it sits in or, for a date
    heading a schedule block, the entries listed under it (`items`)."""
    today = today or date.today()
    matches = list(DATE_RE.finditer(text))
    doc_year = _document_year(matches, today)
    lines = _Lines(text)
    spans_by_line: dict[int, list] = {}
    for m in matches:
        spans_by_line.setdefault(lines.index(m.start()), []).append((m.start(), m.end()))
    date_lines = set(spans_by_line)
    heading_lines = {li for li, spans in spans_by_line.items() if _is_date_only(lines.line(li), spans, lines.starts[li])}

    by_key, out = {}, []
    for n, match in enumerate(matches):
        raw = match.group(0)
        if any(match.group(g) for g in _YEARLESS):
            year, range_end = _year_hint(matches, n, doc_year, text)
            trailing = _TRAILING_WEEKDAY.match(text, match.end())  # "Nov 19 (Thu)" confirms the year too
            to_parse = f"{trailing.group(1)} {raw}" if trailing and not _LEAD_WEEKDAY.match(raw) else raw
            parsed, ambiguous = parse_date(to_parse, year=year, today=today)
            if parsed and range_end and parsed > range_end:  # "20 Dec – 5 Jan 2027"
                try:
                    parsed = parsed.replace(year=parsed.year - 1)
                except ValueError:  # 29 Feb
                    pass
        else:
            parsed, ambiguous = parse_date(raw)
        if parsed is None or not (1900 <= parsed.year <= 2200):
            continue
        label = _label_for(text, match.start())
        context = _context(text, match.start(), match.end())
        event_context = _event_context(text, match.start(), match.end())
        li = lines.index(match.start())
        line = lines.line(li)
        items = []
        if li in heading_lines:
            items = _items_after(lines, li, heading_lines)
            topic = "; ".join(it["what"] for it in items)
            if not topic and li > 0:  # "Project kick-off" / "14 Nov 2026": the heading sits above the date
                above = " ".join(lines.line(li - 1).split())
                topic = above if above and li - 1 not in date_lines and len(above.split()) <= 14 else ""
        else:
            topic = _sentence_with(line, match.start() - lines.starts[li], match.end() - lines.starts[li])
        entry = {
            "text": raw,
            "iso": parsed.isoformat(),
            "label": label,
            "ambiguous": ambiguous,
            "days_from_today": (parsed - today).days,
            "context": context,
            "event_context": event_context,
            "topic": topic[:300],
            "items": items,
        }
        key = (parsed, label) if deduplicate else (parsed, label, context, event_context)
        if key in by_key:
            kept = by_key[key]
            if items and not kept["items"]:  # a schedule block beats a passing mention of the same day
                kept.update(entry)
            continue
        by_key[key] = entry
        out.append(entry)
        if limit is not None and len(out) >= limit:
            break
    out.sort(key=lambda d: d["iso"])
    return out


def schedule(dates: list[dict]) -> list[dict]:
    """Day-by-day plan when the document is laid out as date headings with entries under them."""
    days = [d for d in dates if d.get("items")]
    if len(days) < 2 or sum(len(d["items"]) for d in days) < 3:
        return []
    out = {}
    for d in days:
        out.setdefault(d["iso"], {"iso": d["iso"], "text": d["text"], "days_from_today": d["days_from_today"],
                                  "weekday": date.fromisoformat(d["iso"]).strftime("%A"),
                                  "ambiguous": d["ambiguous"], "items": []})["items"].extend(d["items"])
    return sorted(out.values(), key=lambda d: d["iso"])


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


def is_phone(raw: str) -> bool:
    """A real phone number, not just any long number (Aadhaar, invoice, policy and account numbers are long
    too): an international "+…" number, an Indian mobile (6-9 + 9 digits, optionally 0 / 91 first), a landline
    with its 0 STD code, a 1800 toll-free number, or a "(555) 123-4567" style number."""
    digits = re.sub(r"\D", "", raw)
    if not 10 <= len(digits) <= 13:
        return False
    if raw.lstrip().startswith("+"):
        return True
    if re.fullmatch(r"(?:91|0)?[6-9]\d{9}", digits) or re.fullmatch(r"0\d{9,10}", digits):
        return not re.fullmatch(r"\s*\d{4}\s\d{4}\s\d{4}\s*", raw)  # 4-4-4 groups: an Aadhaar number
    if re.fullmatch(r"18[06]0\d{6,7}", digits):
        return True
    return bool(re.fullmatch(r"\s*\(\d{3}\)\s?\d{3}[\s.-]\d{4}\s*|\s*\d{3}[.-]\d{3}[.-]\d{4}\s*", raw))


def analyze(text: str, today: Optional[date] = None, soon_days: int = 30) -> dict:
    today = today or date.today()
    words = len(re.findall(r"\w+", text))
    dates = extract_dates(text, today)
    phones = [p for p in PHONE_RE.findall(text) if is_phone(p)]
    upcoming = [d for d in dates if d["days_from_today"] >= 0 and d["label"] in {"deadline", "expiry", "review"}]
    plan_days = schedule(dates)
    doc_type = detect_type(text)
    # Two dated lines (an ID card's issue and expiry dates) are not a schedule.
    if len(plan_days) >= 3 and doc_type in {"General document", "Report", "Letter"}:
        doc_type = "Work plan / schedule"
    return {
        "doc_type": doc_type,
        "stats": {
            "words": words,
            "characters": len(text),
            "lines": text.count("\n") + 1 if text else 0,
            "reading_minutes": max(1, round(words / 220)) if words else 0,
        },
        "dates": dates,
        "schedule": plan_days,
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
    for f in info.get("fields", []):
        lines.append(f"{f['label']}: {f['value']}")
    for d in info.get("dates", [])[:max_dates]:
        about = d.get("topic") or d["context"]
        lines.append(f"Date: {d['text']} = {d['iso']} ({d['label']}) — {about[:160]}")
    if info.get("amounts"):
        lines.append("Amounts: " + ", ".join(info["amounts"][:15]))
    if info.get("percentages"):
        lines.append("Percentages: " + ", ".join(info["percentages"][:10]))
    return "\n".join(lines)
