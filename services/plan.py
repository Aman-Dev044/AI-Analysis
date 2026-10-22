"""Understands structured work plans (like t.txt) and pipe/CSV schedules.

Gives the dashboard "today / this week / this month / this quarter" highlights.
"""

import re
from datetime import date, datetime, timedelta
from typing import Optional

_DATE = r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
_QUARTER = re.compile(
    rf"(?m)^---\s*YEAR\s+(\d+)\s*/\s*QUARTER\s+(\d+):\s*(.*?)\s*\(({_DATE})\s+to\s+({_DATE})\)\s*---\s*$", re.I)
_MONTH = re.compile(rf"(?m)^YEAR\s+(\d+)\s*/\s*MONTH\s+(\d+)\s*\(({_DATE})\s+to\s+({_DATE})\)[^\n]*$", re.I)


def _d(value: str) -> Optional[date]:
    value = value.strip()
    for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _body(text: str, start: int) -> str:
    nxt = min((m.start() for p in (_QUARTER, _MONTH) for m in p.finditer(text, start)), default=len(text))
    return " ".join(text[start:nxt].split())


def _goal(body: str) -> Optional[str]:
    m = re.search(r"\bI will\s+(.+?)(?:\.\s|$)", body, re.I)
    if not m:
        return None
    goal = m.group(1).strip()
    return goal[:1].upper() + goal[1:]


def _review(body: str, phrase: str) -> Optional[str]:
    m = re.search(rf"{phrase}\s+({_DATE})", body, re.I)
    parsed = _d(m.group(1)) if m else None
    return parsed.isoformat() if parsed else None


def _themes(text: str) -> dict:
    m = re.search(r"(?im)^Weekday theme:\s*(.+)$", text)
    if not m:
        return {}
    para, themes = m.group(1), {}
    pair = re.search(r"\b(\w+day)\s+and\s+(\w+day)\s+are\s+for\s+(.+?)(?:\.|$)", para, re.I)
    if pair:
        themes[pair.group(1).title()] = themes[pair.group(2).title()] = pair.group(3).strip()
    for day in _WEEKDAYS:
        if day not in themes:
            t = re.search(rf"\b{day}\s+is\s+(?:for|a day for)\s+(.+?)(?:\.|$)", para, re.I)
            if t:
                themes[day] = t.group(1).strip()
    return themes


def structured_plan(text: str, today: Optional[date] = None) -> Optional[dict]:
    today = today or date.today()
    period = re.search(rf"(?im)^Period:\s*({_DATE})\s+to\s+({_DATE})", text)
    if not period:
        return None
    start, end = _d(period.group(1)), _d(period.group(2))
    if not start or not end:
        return None

    quarters = [{
        "year": int(m.group(1)), "number": int(m.group(2)), "title": m.group(3).strip().title(),
        "start": _d(m.group(4)), "end": _d(m.group(5)),
        "focus": _goal(_body(text, m.end())),
        "review_date": _review(_body(text, m.end()), "quarterly review will take place on"),
    } for m in _QUARTER.finditer(text)]
    months = [{
        "year": int(m.group(1)), "number": int(m.group(2)),
        "start": _d(m.group(3)), "end": _d(m.group(4)),
        "focus": _goal(_body(text, m.end())),
        "review_date": _review(_body(text, m.end()), "monthly review is on"),
    } for m in _MONTH.finditer(text)]

    themes = _themes(text)
    routine = re.search(r"(?im)^Daily routine:\s*(.+)$", text)
    weekday = today.strftime("%A")
    if weekday == "Sunday":
        focus, kind = "Rest day — no planned work.", "rest"
    elif weekday == "Saturday":
        focus, kind = "Optional light work or learning (max two hours).", "optional"
    else:
        focus, kind = themes.get(weekday, "Follow the daily routine."), "workday"

    week_start = today - timedelta(days=today.weekday())
    month = next((m for m in months if m["start"] and m["start"] <= today <= m["end"]), None)
    quarter = next((q for q in quarters if q["start"] and q["start"] <= today <= q["end"]), None)
    nxt_month = None if month else next((m for m in months if m["start"] and m["start"] > today), None)
    nxt_quarter = None if quarter else next((q for q in quarters if q["start"] and q["start"] > today), None)

    def ser(item):
        if not item:
            return None
        return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in item.items()}

    routine_items = []
    if routine:
        for m in re.finditer(r"(\d{2}:\d{2}(?:\s*[AP]M)?)-(\d{2}:\d{2}(?:\s*[AP]M)?)\s+([^.]+)\.", routine.group(1)):
            routine_items.append({"from": m.group(1), "to": m.group(2), "what": m.group(3).strip()})

    return {
        "kind": "structured",
        "start": start.isoformat(), "end": end.isoformat(),
        "active": start <= today <= end,
        "progress_percent": round(min(max((today - start).days / max(1, (end - start).days), 0), 1) * 100, 1),
        "today": {"date": today.isoformat(), "weekday": weekday, "type": kind, "focus": focus,
                  "due_date": (today + timedelta(days=max(0, 4 - today.weekday()))).isoformat()},
        "routine": routine_items if kind == "workday" else [],
        "week": [{"day": d, "date": (week_start + timedelta(days=i)).isoformat(),
                  "focus": themes.get(d, "—")} for i, d in enumerate(_WEEKDAYS)],
        "month": ser(month), "next_month": ser(nxt_month),
        "quarter": ser(quarter), "next_quarter": ser(nxt_quarter),
        "counts": {"quarters": len(quarters), "months": len(months)},
    }


def tabular_schedule(text: str, today: Optional[date] = None) -> Optional[dict]:
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2 or "|" not in lines[0]:
        return None
    headers = [re.sub(r"[^a-z0-9]+", "_", c.strip().lower()).strip("_") for c in lines[0].split("|")]

    def col(*names):
        return next((headers.index(n) for n in names if n in headers), None)

    c_date = col("date", "schedule_date", "task_date", "event_date")
    c_act = col("activity", "title", "task", "event", "meeting")
    if c_date is None or c_act is None:
        return None
    c_start, c_end, c_cat, c_loc = col("start_time", "start", "from"), col("end_time", "end", "to"), \
        col("category", "type"), col("location", "venue", "where")
    today = today or date.today()
    entries, all_dates = [], []
    for line in lines[1:]:
        cells = [c.strip() for c in line.split("|")]
        get = lambda i: cells[i] if i is not None and i < len(cells) else ""  # noqa: E731
        d = _d(get(c_date))
        if not d or not get(c_act):
            continue
        all_dates.append(d)
        if d == today:
            entries.append({"activity": get(c_act), "start": get(c_start), "end": get(c_end),
                            "category": get(c_cat), "location": get(c_loc)})
    if not all_dates:
        return None
    return {
        "kind": "tabular",
        "start": min(all_dates).isoformat(), "end": max(all_dates).isoformat(),
        "active": min(all_dates) <= today <= max(all_dates),
        "today": {"date": today.isoformat(), "weekday": today.strftime("%A"),
                  "focus": entries[0]["activity"] if entries else "Nothing scheduled today."},
        "entries": entries,
    }


def detect_plan(text: str, today: Optional[date] = None) -> Optional[dict]:
    return structured_plan(text, today) or tabular_schedule(text, today)
