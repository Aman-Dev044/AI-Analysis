"""Summaries for spreadsheet-like documents (CSV / TSV / pipe tables), built from the cells.

Prose techniques (key sentences, topics) make no sense for rows of a table, so a table gets its own
digest: size, date range, column types, category / priority / status breakdowns, most frequent
entries, what is coming up next and totals for numeric columns. Every value comes from the cells.
"""

import re
from collections import Counter
from datetime import date, timedelta
from typing import Optional

from services.insights import AMOUNT_RE, parse_date

_TIME = re.compile(r"^\d{1,2}[:.]\d{2}(?:\s?[ap]\.?m\.?)?$", re.I)
_NUM = re.compile(r"^[-+]?(?:₹|rs\.?|inr|\$|€|£)?\s?\d[\d,]*(?:\.\d+)?\s?%?$", re.I)
ROLE_NAMES = {
    "task": ("task", "activity", "title", "event", "description", "item", "subject", "meeting", "name", "particulars"),
    "category": ("category", "type", "group", "department", "section", "class"),
    "priority": ("priority", "importance", "urgency", "severity"),
    "status": ("status", "state", "progress", "stage"),
    "start": ("start", "start_time", "from", "time", "begin"),
    "end": ("end", "end_time", "to", "finish"),
}
COUNTS = {"brief": 3, "standard": 5, "comprehensive": 8}


def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def parse(text: str) -> Optional[dict]:
    """{headers, rows} when the text is a table (most lines are ' | '-separated with a steady column count)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 3:
        return None
    piped = [ln for ln in lines if " | " in ln or ln.count("|") >= 2]
    if len(piped) / len(lines) < 0.8:
        return None
    headers = [h.strip() for h in lines[0].split("|")]
    n = len(headers)
    if n < 2 or not all(headers) or sum(bool(parse_date(h)[0]) or _NUM.match(h) is not None for h in headers) > n // 2:
        return None  # the first line is data, not a header row
    rows = []
    for ln in lines[1:]:
        cells = [c.strip() for c in ln.split("|")]
        if len(cells) == n:
            rows.append(cells)
        elif abs(len(cells) - n) == 1:
            rows.append((cells + [""])[:n])
    if len(rows) < 2 or len(rows) < 0.7 * (len(lines) - 1):
        return None
    return {"headers": headers, "keys": [_key(h) for h in headers], "rows": rows}


# ------------------------------------------------------------------ column analysis
def _column_kind(values: list[str]) -> str:
    vals = [v for v in values if v]
    if not vals:
        return "empty"
    sample = vals[:400]
    share = lambda pred: sum(1 for v in sample if pred(v)) / len(sample)  # noqa: E731
    if share(lambda v: parse_date(v)[0] is not None) >= 0.8:
        return "date"
    if share(lambda v: _TIME.match(v) is not None) >= 0.8:
        return "time"
    if share(lambda v: _NUM.match(v) is not None) >= 0.8:
        return "number"
    distinct = len(set(vals))
    if distinct <= max(12, len(vals) * 0.2) and distinct < len(vals):
        return "category"
    return "text"


def _number(v: str) -> Optional[float]:
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", v)
    try:
        return float(m.group(0).replace(",", "")) if m else None
    except ValueError:
        return None


def _fmt_num(x: float) -> str:
    return f"{x:,.0f}" if abs(x - round(x)) < 1e-9 else f"{x:,.2f}"


def analyze(table: dict, today: Optional[date] = None) -> dict:
    today = today or date.today()
    headers, keys, rows = table["headers"], table["keys"], table["rows"]
    columns = []
    for i, h in enumerate(headers):
        values = [r[i] for r in rows]
        columns.append({"index": i, "name": h, "key": keys[i], "kind": _column_kind(values), "values": values})

    def role(name):
        names = ROLE_NAMES[name]
        hit = next((c for c in columns if c["key"] in names), None)
        return hit or next((c for c in columns if any(c["key"].startswith(n) or c["key"].endswith(n) for n in names)), None)

    roles = {r: role(r) for r in ROLE_NAMES}
    date_col = next((c for c in columns if c["kind"] == "date"), None)
    if roles["task"] is None or roles["task"]["kind"] not in {"text", "category"}:
        roles["task"] = next((c for c in columns if c["kind"] == "text"), None)
    dates = []
    if date_col:
        for k, v in enumerate(date_col["values"]):
            d = parse_date(v)[0]
            if d:
                dates.append((d, k))
    return {"columns": columns, "roles": roles, "date_col": date_col, "dates": dates, "today": today,
            "rows": rows, "headers": headers}


def doc_type(info: dict) -> str:
    return "Schedule" if info["date_col"] and info["roles"]["task"] else "Spreadsheet / table"


# ------------------------------------------------------------------ markdown
def _cell(v: str, width: int = 70) -> str:
    v = v.replace("|", "/").replace("*", "∗").strip()
    return v if len(v) <= width else v[:width - 1].rstrip() + "…"


def _fmt_date(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"


def _breakdown(col: dict, top: int) -> str:
    counts = Counter(v for v in col["values"] if v)
    total = sum(counts.values()) or 1
    parts = [f"{_cell(v, 30)} **{c}** ({round(c * 100 / total)}%)" for v, c in counts.most_common(top)]
    rest = len(counts) - top
    return f"- **{col['name']}:** " + " · ".join(parts) + (f" · +{rest} more" if rest > 0 else "")


def _row_table(info: dict, picks: list[int], limit: int) -> str:
    r = info["roles"]
    cols = [c for c in (info["date_col"], r["start"], r["end"], r["task"], r["category"], r["priority"], r["status"]) if c]
    cols = list({c["index"]: c for c in cols}.values())
    if not cols:
        cols = info["columns"][:5]
    head = "| " + " | ".join(c["name"] for c in cols) + " |\n|" + "---|" * len(cols)
    body = "\n".join("| " + " | ".join(_cell(info["rows"][k][c["index"]], 60) or "—" for c in cols) + " |"
                     for k in picks[:limit])
    return head + "\n" + body


def summarize(table: dict, *, mode: str = "smart", length: str = "standard", title: str = "",
              instructions: str = "", today: Optional[date] = None) -> str:
    info = analyze(table, today)
    rows, cols, roles = info["rows"], info["columns"], info["roles"]
    n = COUNTS.get(length, 5) + (3 if mode == "detailed" else 0)
    kind = doc_type(info)
    parts = [f"## {title or kind}", f"*{kind} · {len(rows):,} rows · {len(cols)} columns*"]

    # Overview
    if info["dates"]:
        ds = sorted(d for d, _ in info["dates"])
        days = len({d for d in ds})
        per_day = len(info["dates"]) / max(1, days)
        noun = "entries" if kind == "Schedule" else "rows"
        overview = (f"This {kind.lower().split(' /')[0]} has **{len(rows):,}** {noun} from **{_fmt_date(ds[0])}** to "
                    f"**{_fmt_date(ds[-1])}** across **{days}** day(s), about **{per_day:.0f}** per day.")
        if ds[0] <= info["today"] <= ds[-1]:
            overview += " It is **in progress** today."
        elif info["today"] < ds[0]:
            overview += f" It starts in **{(ds[0] - info['today']).days}** day(s)."
        else:
            overview += " All of its dates are in the past."
    else:
        overview = (f"This table has **{len(rows):,}** rows and **{len(cols)}** columns: "
                    + ", ".join(c["name"] for c in cols[:8]) + ("…" if len(cols) > 8 else "") + ".")
    parts.append(overview)

    # Custom: rows that match the user's words
    if mode == "custom" and instructions.strip():
        terms = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", instructions)} - {
            "summary", "summarise", "summarize", "show", "list", "give", "table", "the", "and", "all", "with"}
        hits = [k for k, r in enumerate(rows) if terms and any(t in " ".join(r).lower() for t in terms)]
        parts.append(f"> Matching your request: *{instructions.strip()[:200]}*")
        parts.append(f"### Matching rows ({len(hits)})\n\n" + _row_table(info, hits, 12 + n) if hits
                     else "### Matching rows\n\nNo rows mention those words.")

    # Breakdowns
    cats = [c for c in (roles["category"], roles["priority"], roles["status"]) if c and c["kind"] in {"category", "text"}]
    cats += [c for c in cols if c["kind"] == "category" and c not in cats and c is not roles["task"]]
    if cats:
        parts.append("### Breakdown\n\n" + "\n".join(_breakdown(c, 4 if length == "brief" else 6) for c in cats[:3 + (mode == "detailed")]))

    # Most frequent entries
    task = roles["task"]
    if task:
        counts = Counter(v for v in task["values"] if v)
        repeated = [(v, c) for v, c in counts.most_common(n) if c > 1]
        if repeated:
            parts.append(f"### Most frequent {task['name'].lower()}\n\n| {task['name']} | Times |\n|---|---|\n"
                         + "\n".join(f"| {_cell(v)} | **{c}** |" for v, c in repeated))
        elif mode in {"detailed", "bullets"}:
            parts.append(f"### Sample {task['name'].lower()}\n\n" + "\n".join(f"- {_cell(v, 120)}" for v in task["values"][:n]))

    # What happens next (or the latest rows when everything is in the past)
    if info["dates"]:
        today = info["today"]
        horizon = today + timedelta(days=14 if mode == "dates" else 7)
        upcoming = [k for d, k in sorted(info["dates"]) if today <= d <= horizon]
        if upcoming:
            limit = 20 if mode in {"dates", "detailed"} else 8
            parts.append(f"### Coming up (next {(horizon - today).days} days · {len(upcoming)} entries)\n\n"
                         + _row_table(info, upcoming, limit)
                         + (f"\n\n*Showing {limit} of {len(upcoming)}.*" if len(upcoming) > limit else ""))
        pr = roles["priority"]
        if pr and mode in {"actions", "executive", "smart", "dates"}:
            high = [k for d, k in sorted(info["dates"]) if d >= today and re.search(r"high|urgent|critical|p1", rows[k][pr["index"]], re.I)]
            if high:
                parts.append(f"### High priority ahead ({len(high)})\n\n" + _row_table(info, high, 8))

    # Numbers
    nums = [c for c in cols if c["kind"] == "number"]
    if nums:
        lines = []
        for c in nums[:4]:
            vals = [x for x in (_number(v) for v in c["values"]) if x is not None]
            if vals:
                money = any(AMOUNT_RE.search(v) for v in c["values"][:50])
                total = f"total **{_fmt_num(sum(vals))}** · " if money or "amount" in c["key"] or "total" in c["key"] else ""
                lines.append(f"- **{c['name']}:** {total}average **{_fmt_num(sum(vals) / len(vals))}** · "
                             f"min **{_fmt_num(min(vals))}** · max **{_fmt_num(max(vals))}**")
        if lines:
            parts.append("### Numbers\n\n" + "\n".join(lines))

    # Columns overview for detailed / study
    if mode in {"detailed", "study", "bullets"}:
        label = {"date": "Date", "time": "Time", "number": "Number", "category": "Category", "text": "Text", "empty": "Empty"}
        parts.append("### Columns\n\n| Column | Type | Example |\n|---|---|---|\n" + "\n".join(
            f"| {_cell(c['name'], 40)} | {label[c['kind']]} | {_cell(next((v for v in c['values'] if v), '—'), 50)} |"
            for c in cols))
    return "\n\n".join(parts)


# ------------------------------------------------------------------ Q&A
_QUESTION_WORDS = {"what", "when", "which", "who", "how", "many", "much", "the", "are", "is", "for", "and", "this", "that",
                   "kya", "kab", "hai", "hain", "kitne", "kitna", "kitni", "ka", "ki", "ke", "me", "mein", "batao", "show",
                   "list", "give", "all", "do", "does", "there", "any", "table", "schedule", "rows", "row"}


def answer(table: dict, question: str, today: Optional[date] = None) -> str:
    """Rows that match the question's words (and a count when asked "how many")."""
    info = analyze(table, today)
    rows, q = info["rows"], question.lower()
    terms = {w for w in re.findall(r"[a-z0-9]{3,}", q) if w not in _QUESTION_WORDS}
    when = None
    if re.search(r"\b(today|aaj)\b", q):
        when = info["today"]
    elif re.search(r"\b(tomorrow|kal)\b", q):
        when = info["today"] + timedelta(days=1)
    by_date = {k: d for d, k in info["dates"]}
    hits = [k for k, r in enumerate(rows)
            if (when is None or by_date.get(k) == when)
            and (not terms or when is not None and not (terms - {"today", "aaj", "tomorrow", "kal"})
                 or any(t in " ".join(r).lower() for t in terms - {"today", "aaj", "tomorrow", "kal"}))]
    if not hits:
        return ("I could not find rows matching that in this table. It has **%d** rows with the columns: %s."
                % (len(rows), ", ".join(info["headers"])))
    head = f"**{len(hits)}** matching row(s)" + (f" on **{_fmt_date(when)}**" if when else "") + "."
    if re.search(r"how many|kitne|kitni|count|number of", q):
        return head
    return head + "\n\n" + _row_table(info, hits, 15) + (f"\n\n*Showing 15 of {len(hits)}.*" if len(hits) > 15 else "")
