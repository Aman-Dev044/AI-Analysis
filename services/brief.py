"""Smart brief: a fast, source-grounded summary built for small models on CPU servers.

Facts (fields, key dates, validity status, amounts, actions, key sentences) are extracted
deterministically, so they are exact and instant. The model only writes a short overview from those
facts, and every sentence it writes is checked against the source: a sentence with a date, number or
name that is not in the document is dropped. Without Ollama the brief still works, minus the prose.
"""

import re
from datetime import date
from typing import Callable, Optional

from config import Config
from services import extractive, fields as fields_mod, ollama_client
from services.insights import DATE_RE, parse_date

OverviewFn = Callable[[Optional[str]], None]  # streamed overview text (None while not started)

POINTS = {"brief": 3, "standard": 5, "comprehensive": 8}
SENTENCES = {"brief": "2-3", "standard": "3-4", "comprehensive": "4-6"}
NUM_PREDICT = {"brief": 160, "standard": 240, "comprehensive": 380}
ID_TYPES = {"Driving licence", "Passport", "PAN card", "Aadhaar card", "Certificate", "Insurance policy",
            "Marksheet / Result"}
# Documents whose own validity is the point. Elsewhere an "expires on" in the text (e.g. a vendor contract
# mentioned in a report) is just a date, not the document's status, unless it is a labelled field.
VALIDITY_TYPES = ID_TYPES | {"Contract / Agreement"}
TOPICS = {"brief": 4, "standard": 5, "comprehensive": 7}
FIGURES = {"brief": 4, "standard": 6, "comprehensive": 10}
SUBJECT_KEYS = ("name", "billed_to")
STATUS_ROLES = {"expiry_date"}


# ------------------------------------------------------------------ facts
def _rel(days: int) -> str:
    if days == 0:
        return "today"
    n, unit = abs(days), "day"
    if n >= 730:
        n, unit = round(n / 365), "year"
    elif n >= 60:
        n, unit = round(n / 30), "month"
    word = f"{n} {unit}{'s' if n != 1 else ''}"
    return f"in {word}" if days > 0 else f"{word} ago"


def collect(text: str, insights: dict, today: Optional[date] = None, length: str = "standard") -> dict:
    today = today or date.today()
    flds = insights.get("fields")
    if flds is None:
        flds = fields_mod.extract_fields(text, today)
    else:  # stored fields: refresh relative days
        for f in flds:
            if f.get("iso"):
                f["days_from_today"] = (date.fromisoformat(f["iso"]) - today).days
    dates = fields_mod.key_dates(flds, insights)
    doc_type = insights.get("doc_type") or "General document"
    sents = extractive.sentences(text)
    for d in dates:
        d["days_from_today"] = (date.fromisoformat(d["iso"]) - today).days
        # What the date is about, from the sentence it appears in ("Regional heads should submit forecasts").
        src = "" if d.get("source") == "field" else next(
            (s for s in sents if d["text"] in s and not extractive.is_label_line(s)), "")
        d["detail"] = extractive.context(src, d["text"]) if src else ""

    expiry = None
    expiries = [d for d in dates if d["role"] == "expiry_date" and (d.get("source") == "field" or doc_type in VALIDITY_TYPES)]
    if expiries:
        e = max(expiries, key=lambda d: d["iso"])
        days = e["days_from_today"]
        status = "expired" if days < 0 else "expiring_soon" if days <= Config.EXPIRING_SOON_DAYS else "valid"
        expiry = {"text": e["text"], "iso": e["iso"], "days": days, "status": status, "ambiguous": e["ambiguous"]}

    by_key = {f["key"]: f for f in flds}
    is_id = doc_type in ID_TYPES
    points = [] if is_id else extractive.key_sentences(text, limit=POINTS.get(length, 5))
    return {
        "doc_type": doc_type,
        "title": "" if is_id else extractive.doc_title(text),
        "topics": [] if is_id else extractive.keyphrases(text, TOPICS.get(length, 5)),
        "figures": [] if is_id else extractive.figures(text, FIGURES.get(length, 6)),
        "words": (insights.get("stats") or {}).get("words") or len(text.split()),
        "fields": flds,
        "by_key": by_key,
        "dates": dates,
        "expiry": expiry,
        "amounts": insights.get("amounts", [])[:6],
        "emails": insights.get("emails", [])[:2],
        "phones": insights.get("phones", [])[:2],
        "points": points,
        "actions": _actions(dates, expiry, insights, today),
    }


def _actions(dates: list[dict], expiry: Optional[dict], insights: dict, today: date) -> list[str]:
    out = []
    if expiry:
        if expiry["status"] == "expired":
            out.append(f"<u>Expired {_rel(expiry['days'])}</u> on **{expiry['text']}** — renew it before using it again.")
        elif expiry["status"] == "expiring_soon":
            out.append(f"<u>Renew before **{expiry['text']}**</u> — only {expiry['days']} day(s) left.")
    for d in dates:
        what = f" — {d['detail']}" if d.get("detail") else ""
        if d["role"] == "renewal_date" and d["days_from_today"] >= 0:
            out.append(f"Renewal due on **{d['text']}** ({_rel(d['days_from_today'])}){what}.")
        elif d["role"] == "due_date":
            if d["days_from_today"] < 0:
                out.append(f"<u>Deadline **{d['text']}** has passed</u> ({_rel(d['days_from_today'])}){what}.")
            else:
                out.append(f"Deadline **{d['text']}** ({_rel(d['days_from_today'])}){what}.")
    seen = {d["iso"] for d in dates if d["role"] in {"due_date", "renewal_date", "expiry_date"}}
    for d in insights.get("dates", []):
        if d["label"] == "deadline" and d["iso"] not in seen and 0 <= (date.fromisoformat(d["iso"]) - today).days <= 365:
            out.append(f"Deadline **{d['text']}** ({_rel((date.fromisoformat(d['iso']) - today).days)}): {d['context'][:110]}")
            seen.add(d["iso"])
            if len(out) >= 6:
                break
    return [a.replace("….", "…") for a in out]


# ------------------------------------------------------------------ markdown
def _cell(value: str) -> str:
    return value.replace("|", "/").replace("<", "‹").replace("*", "∗").strip()


def _status_line(expiry: Optional[dict]) -> str:
    if not expiry:
        return ""
    line = _status_text(expiry)
    if expiry["ambiguous"]:
        line += " Date read as day/month/year — check the original."
    return line


def _status_text(expiry: dict) -> str:
    t, days = expiry["text"], expiry["days"]
    if expiry["status"] == "expired":
        return f"> **Status:** <u>Expired</u> on **{t}** ({_rel(days)})."
    if expiry["status"] == "expiring_soon":
        return f"> **Status:** <u>Expiring soon</u> — valid till **{t}** ({_rel(days)})."
    return f"> **Status:** Valid till **{t}** ({_rel(days)})."


def heading(facts: dict, title: str = "") -> str:
    """The document's own title for prose documents; the document type for IDs and records."""
    doc_type = facts["doc_type"]
    if doc_type in ID_TYPES:
        return doc_type
    return facts.get("title") or (doc_type if doc_type != "General document" else "") or title or "Document summary"


def header(facts: dict, title: str = "") -> list[str]:
    """Heading, a one-line meta row (type, length) and the validity status, if any."""
    head = heading(facts, title)
    parts = [f"## {head}"]
    meta = []
    if facts["doc_type"] not in {"General document", head}:
        meta.append(facts["doc_type"])
    words = facts.get("words") or 0
    if words >= 150:
        meta.append(f"{words:,} words · about {max(1, round(words / 220))} min read")
    if meta:
        parts.append("*" + " · ".join(meta) + "*")
    status = _status_line(facts["expiry"])
    if status:
        parts.append(status)
    return parts


def details_table(facts: dict) -> str:
    rows = [(f["label"], f["value"]) for f in facts["fields"] if f["kind"] != "date"]
    if (not any(f["kind"] == "amount" for f in facts["fields"]) and facts["amounts"]
            and len(facts.get("figures") or []) < 2):
        rows.append(("Amounts mentioned", ", ".join(facts["amounts"][:5])))
    if facts["emails"]:
        rows.append(("Email", ", ".join(facts["emails"])))
    if facts["phones"]:
        rows.append(("Phone", ", ".join(facts["phones"])))
    if not rows:
        return ""
    return "### Key details\n\n| Detail | Value |\n|---|---|\n" + "\n".join(
        f"| {_cell(k)} | **{_cell(v)}** |" for k, v in rows)


def figures_table(facts: dict) -> str:
    figs = facts.get("figures") or []
    if len(figs) < 2:
        return ""
    return "### Key figures\n\n| Figure | What it refers to |\n|---|---|\n" + "\n".join(
        f"| **{_cell(v)}** | {_cell(what)} |" for v, what in figs)


def date_what(d: dict) -> str:
    return f"{d['what']}: {d['detail']}" if d.get("detail") else d["what"]


def dates_table(facts: dict, title: str = "### Important dates") -> str:
    if not facts["dates"]:
        return ""
    lines = []
    for d in facts["dates"]:
        when = _rel(d["days_from_today"])
        if d["role"] in {"expiry_date", "due_date", "renewal_date"} and d["days_from_today"] < 0:
            when = f"<u>{when}</u>"
        lines.append(f"| **{d['text']}** | {_cell(date_what(d))} | {when} |")
    return f"{title}\n\n| Date | What | When |\n|---|---|---|\n" + "\n".join(lines)


def topics_line(facts: dict) -> str:
    topics = facts.get("topics") or []
    return "**Main topics:** " + " · ".join(topics) if len(topics) >= 2 else ""


def mentioned(sentence: str, text: str) -> bool:
    """True when `text` (an overview, earlier bullets) already contains this source sentence."""
    core = extractive.tidy(sentence).replace("**", "").rstrip(".!?")
    return bool(core) and core in text.replace("**", "")


def point_lines(points: list[str], skip: str = "") -> str:
    """Key sentences as bullets: list markers removed, properly ended, dates and amounts bold."""
    return "\n".join(f"- {extractive.bold_facts(extractive.tidy(p))}" for p in points if not mentioned(p, skip))


def compose(facts: dict, overview: Optional[str], title: str = "") -> str:
    parts = header(facts, title)
    overview = overview.strip() if overview and overview.strip() else ""
    parts.append(overview or "*Writing overview…*")
    parts.append(topics_line(facts))

    points = point_lines(facts["points"], overview)
    blocks = [details_table(facts), dates_table(facts)]
    if points:  # prose documents: what it says first, then the reference tables
        blocks = ["### Key points\n\n" + points, figures_table(facts)] + blocks
    parts += blocks
    if facts["actions"]:
        parts.append("### Action needed\n\n" + "\n".join(f"- {a}" for a in facts["actions"]))
    return "\n\n".join(p for p in parts if p)


# ------------------------------------------------------------------ overview
def fallback_overview(facts: dict) -> str:
    k = facts["by_key"]
    subject = next((k[x]["value"] for x in SUBJECT_KEYS if x in k), None)
    doc = facts["doc_type"] if facts["doc_type"] != "General document" else "This document"
    first = doc if doc == "This document" else f"This {doc.lower()}"
    bits = []
    if subject:
        rel = f" (father / guardian **{k['relation']['value']}**)" if "relation" in k else ""
        bits.append(f"belongs to **{subject}**{rel}")
    elif "author" in k:
        bits.append(f"was prepared by **{k['author']['value']}**")
    issued = k.get("issue_date") or k.get("created_date") or k.get("doc_date")
    if issued:
        by = f" by **{k['authority']['value']}**" if "authority" in k else ""
        verb = "was issued on" if issued["key"] == "issue_date" else "is dated"
        bits.append(f"{verb} **{issued['value']}**{by}")
    if facts["expiry"]:
        bits.append(f"is valid till **{facts['expiry']['text']}**")
    sentence = ""
    if bits:
        joined = bits[0] if len(bits) == 1 else ", ".join(bits[:-1]) + " and " + bits[-1]
        sentence = f"{first} {joined}."
        if doc.lower().endswith(("notes", "minutes")):  # plural document types
            sentence = (sentence.replace("This ", "These ", 1).replace(" belongs ", " belong ")
                        .replace(" was issued", " were issued").replace(" is dated", " are dated")
                        .replace(" is valid", " are valid").replace(" was prepared", " were prepared"))
    ident = next((f for f in facts["fields"] if f["kind"] == "id"), None)
    extra = [f"{ident['label']} **{ident['value']}**."] if ident else []
    total = k.get("total")
    if total:
        extra.append(f"Total amount **{total['value']}**.")
    if not subject and facts["points"]:
        extra.append(extractive.bold_facts(extractive.tidy(facts["points"][0])))
    return " ".join(x for x in [sentence] + extra if x) or "No clear summary facts were found in this document."


def _facts_text(facts: dict) -> str:
    lines = [f"Document type: {facts['doc_type']}"]
    if facts.get("title"):
        lines.append(f"Title: {facts['title']}")
    lines += [f"{f['label']}: {f['value']}" for f in facts["fields"] if f["kind"] != "date"]
    lines += [f"{d['what']}: {d['text']}" + (f" ({d['detail']})" if d.get("detail") else "") for d in facts["dates"]]
    if facts.get("topics"):
        lines.append("Main topics: " + ", ".join(facts["topics"]))
    if facts["expiry"]:
        e = facts["expiry"]
        lines.append({"expired": f"Status: expired ({_rel(e['days'])})",
                      "expiring_soon": f"Status: expiring soon ({_rel(e['days'])})",
                      "valid": f"Status: valid ({_rel(e['days'])})"}[e["status"]])
    if facts["amounts"]:
        lines.append("Amounts: " + ", ".join(facts["amounts"]))
    return "\n".join(lines)


def _messages(facts: dict, text: str, length: str, language_rule: str, instructions: str) -> list[dict]:
    excerpt = text if len(text) <= 3500 else extractive.condense(text, 3500)
    task = (f"Write a {SENTENCES.get(length, '3-4')} sentence overview: what this document is, who or what it is "
            "about, and what matters most (validity, amounts, obligations, decisions). Use ONLY the facts and text "
            "below. Copy names, numbers and dates exactly as written and make them **bold**. Do not repeat a fact. "
            "No headings, no lists, no introduction, no closing remarks. " + language_rule)
    if instructions.strip():
        task += f" Extra instructions: {instructions.strip()[:500]}"
    return [
        {"role": "system", "content": "You write short, precise, factual document overviews. You never invent "
                                      "names, numbers or dates."},
        {"role": "user", "content": f"{task}\n\nVERIFIED FACTS:\n{_facts_text(facts)}\n\n<document>\n{excerpt}\n</document>"},
    ]


def _alnum(s: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", s.lower())


_PROPER = re.compile(r"\b[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+\b")
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


# Ordinary document vocabulary a model may use around facts without inventing anything.
GENERIC = set("""
document documents licence license licences number holder card policy certificate date dates issue issued issuing
expiry expires expired expiring valid validity until till upto name named father mother guardian husband wife son
daughter address resident residing class vehicle vehicles total amount amounts invoice receipt account bank government
india indian state department authority office details detail record registration identity identification proof type
renewal renew renewed due payment payable paid tax status summary overview important key current currently days months
years year month day ago left remaining note person individual owner bearer applicant customer insured premium sum cover
agreement contract party parties terms term period effective start end birth born blood group gender male female
the this that these those from with within under over
""".split())


def _unknown_words(phrase: str, ground_words: set) -> list[str]:
    words = re.findall(r"[a-z]+", phrase.lower())
    return [w for w in words if len(w) >= 3 and w not in ground_words and w not in GENERIC
            and w not in extractive.STOPWORDS]


def verify(overview: str, source: str, facts_text: str, check_names: bool = True) -> str:
    """Drop overview sentences that mention dates, numbers or names absent from the document."""
    ground = source + "\n" + facts_text
    ground_digits = re.sub(r"[,\s]", "", ground)
    ground_words = set(re.findall(r"[a-z]+", ground.lower()))
    ground_dates = {p.isoformat() for p in (parse_date(m.group(0))[0] for m in DATE_RE.finditer(ground)) if p}

    kept, seen = [], set()
    for sent in re.split(r"(?<=[.!?।])\s+", overview.strip()):
        if not sent.strip():
            continue
        ok = True
        plain = sent
        for m in DATE_RE.finditer(sent):
            parsed = parse_date(m.group(0))[0]
            if parsed and parsed.isoformat() not in ground_dates:
                ok = False
            plain = plain.replace(m.group(0), " ")
        for num in _NUM.findall(plain):
            digits = num.replace(",", "").rstrip(".")
            if len(digits.replace(".", "")) >= 2 and digits not in ground_digits:
                ok = False
        if check_names:
            phrases = re.findall(r"\*\*(.+?)\*\*", sent) + _PROPER.findall(sent.replace("**", ""))
            if any(_unknown_words(p, ground_words) for p in phrases):
                ok = False
        key = _alnum(sent)
        if ok and key not in seen:
            kept.append(sent.strip())
            seen.add(key)
    return " ".join(kept)


def smart_summary(
    text: str,
    insights: dict,
    *,
    length: str = "standard",
    language: str = "English",
    language_rule: str = "",
    instructions: str = "",
    title: str = "",
    model: Optional[str] = None,
    progress: Optional[Callable[[int, str, Optional[str]], None]] = None,
) -> str:
    progress = progress or (lambda *_: None)
    facts = collect(text, insights, length=length)
    progress(20, "Key facts ready", compose(facts, None, title))

    overview = ""
    if Config.SMART_AI_OVERVIEW and Config.AI_BACKEND != "rules":
        expected = NUM_PREDICT.get(length, 240) * 4

        def on_token(partial: str):
            progress(min(95, 25 + int(len(partial) / expected * 70)), "Writing overview", compose(facts, partial, title))

        try:
            raw = ollama_client.chat(_messages(facts, text, length, language_rule, instructions), model=model,
                                     temperature=0.1, num_predict=NUM_PREDICT.get(length, 240),
                                     num_ctx=4096, on_token=on_token)
            raw = re.sub(r"(?m)^\s*(#+\s.*|[-*]\s+)", "", raw).strip()  # prose only
            overview = verify(raw, text, _facts_text(facts), check_names=language == "English")
        except ollama_client.OllamaError:
            overview = ""
    return compose(facts, overview or fallback_overview(facts), title)
