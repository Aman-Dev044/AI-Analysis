"""Every summary style and document Q&A without a language model (AI_BACKEND=rules, or Ollama down).

Output is assembled from source text only: rule-extracted fields and dates (services.fields / insights),
key sentences (services.extractive) and cue-word classification, so it is instant on any CPU and
never contains anything that is not in the document.
"""

import re
from datetime import date
from typing import Optional

from services import brief, extractive, tabular
from services.insights import AMOUNT_RE, DATE_RE, PERCENT_RE, parse_date

SCALE = {"brief": 0.6, "standard": 1.0, "comprehensive": 1.8}

DECISION_RE = re.compile(r"\b(decid\w*|decision|resolved|approv\w*|agreed|recommend\w*|propos\w*|conclud\w*|"
                         r"selected|finali[sz]ed|adopted|suggest\w*)\b", re.I)
RISK_RE = re.compile(r"\b(risk\w*|penalt\w*|fine[sd]?|delay\w*|breach\w*|terminat\w*|liabil\w*|loss\w*|concern\w*|"
                     r"issue[s]?|problem\w*|fail\w*|warning|overdue|default\w*|dispute\w*|non-?compliance|expired?|"
                     r"barrier\w*|challeng\w*|obstacle\w*|lag(?:s|ging)?\s+behind|shortage\w*|threat\w*|uneven|"
                     r"uncertain\w*)\b", re.I)
ACTION_STRONG = re.compile(r"\b(must|shall|should|required?|mandatory|need(?:s)? to|has to|have to|ensure|"
                           r"deadline|due(?!\s+to\b)|last date|on or before|by\s+\d)\b", re.I)
ACTION_WILL = re.compile(r"\b(will|is to|are to|to be)\b", re.I)
IMPERATIVE = re.compile(r"^(please\s+)?(submit|pay|send|provide|deliver|renew|sign|prepare|review|update|apply|register|"
                        r"attend|contact|complete|ensure|share|call|check|follow|bring|keep|carry|fill|upload)\b", re.I)


class _ActionMatcher:
    """Sentences that ask someone to do something (not past-tense reports)."""

    def search(self, s: str) -> bool:
        return bool(ACTION_STRONG.search(s) or IMPERATIVE.search(s) or (ACTION_WILL.search(s) and DATE_RE.search(s)))


ACTION_RE = _ActionMatcher()
HIGH_RE = re.compile(r"\b(must|mandatory|immediately|urgent\w*|penalt\w*|deadline|last date|strictly|required)\b", re.I)
MEDIUM_RE = re.compile(r"\b(shall|should|need(?:s|ed)? to|has to|have to|ensure|due(?!\s+to\b))\b", re.I)


# ------------------------------------------------------------------ helpers
def _n(base: int, length: str) -> int:
    return max(1, round(base * SCALE.get(length, 1.0)))


def _top(sents: list[str], n: int) -> list[str]:
    if not sents:
        return []
    return extractive.key_sentences("\n\n".join(sents), limit=n, min_words=4, max_words=80)


_bold_facts = extractive.bold_facts


def _line(s: str, owner: bool = False) -> str:
    s = extractive.tidy(s)
    return _bold_facts(extractive.bold_owner(s) if owner else s)


def _bullets(items: list[str], checkbox: bool = False, owner: bool = False) -> str:
    mark = "- [ ] " if checkbox else "- "
    return "\n".join(mark + _line(i, owner or checkbox) for i in items)


def _sents(text: str) -> list[str]:
    return [s for s in extractive.sentences(text) if 4 <= len(s.split()) <= 90 and "|" not in s
            and not extractive.is_heading(s) and not extractive.is_label_line(s)]


def _overview_and_points(text: str, facts: dict, n: int) -> tuple[str, list[str]]:
    overview = brief.fallback_overview(facts)
    points = facts["points"] or _top(_sents(text), n + 1)
    return overview, [p for p in points if not brief.mentioned(p, overview)][:n]


def _matching(sents: list[str], rx, exclude: set = frozenset()) -> list[str]:
    return [s for s in sents if rx.search(s) and s not in exclude]


def _head(facts: dict, title: str) -> list[str]:
    return brief.header(facts, title)


def _details_table(facts: dict) -> str:
    return brief.details_table(facts)


def _dates_table(facts: dict, title: str = "### Important dates") -> str:
    return brief.dates_table(facts, title)


def _extra_actions(actions: list[str], sents: list[str]) -> list[str]:
    """Rule-made action lines whose date is not already covered by a quoted task sentence."""
    def covered(a):
        m = re.search(r"\*\*(.+?)\*\*", a)
        return m and any(m.group(1) in s for s in sents)
    return [a for a in actions if not covered(a)]


_SECTION_NUM = re.compile(r"^(?:\d+(?:\.\d+)*|[IVX]+)[.)]\s+")
_CLOSING = re.compile(r"\b(conclu\w*|summary|closing|final remarks|way forward)\b", re.I)


def _sections(text: str) -> list[tuple[str, str]]:
    """(heading, body) pairs from headings in the text: Markdown #, ALL CAPS, numbered or 'Title:' lines."""
    out, current, body = [], None, []
    for line in text.splitlines():
        s = line.strip()
        words = s.split()
        is_heading = bool(s) and len(words) <= 10 and not s.endswith((".", ",", ";")) and (
            s.startswith("#") or re.match(r"^(\d+(\.\d+)*|[IVX]+)[.)]\s+[A-Z]", s) is not None
            or (sum(c.isupper() for c in s if c.isalpha()) / max(1, sum(c.isalpha() for c in s)) > 0.8 and len(s) >= 4)
            or (s.endswith(":") and len(words) <= 6))
        if is_heading:
            if current is not None or body:
                out.append((current or "Introduction", "\n".join(body)))
            current, body = extractive.title_case(_SECTION_NUM.sub("", s.strip("#:*- ").strip())), []
        else:
            body.append(line)
    if current is not None or body:
        out.append((current or "Introduction", "\n".join(body)))
    return [(h, b) for h, b in out if len(_sents(b)) >= 1]


def _keywords(text: str, n: int) -> list[str]:
    from collections import Counter
    body = " ".join(_sents(text))  # sentences only: headings and label lines would dominate otherwise
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z-]{3,}", body) if w.lower() not in extractive.STOPWORDS
             and not w.isupper()]
    counts = Counter(w.lower() for w in words)
    caps = {}
    for w in words:
        caps.setdefault(w.lower(), w)
    return [caps[w] for w, c in counts.most_common(n * 3) if c >= 2][:n]


# ------------------------------------------------------------------ styles
def _short(text, facts, length, title, **_):
    overview, points = _overview_and_points(text, facts, _n(5, length))
    parts = _head(facts, title) + [overview, brief.topics_line(facts)]
    if points:
        parts.append("### Key points\n\n" + _bullets(points))
    elif facts["fields"]:
        parts.append(_details_table(facts))
    return parts


def _detailed(text, facts, length, title, **_):
    parts = _head(facts, title) + ["## Overview", brief.fallback_overview(facts), brief.topics_line(facts)]
    for block in (_details_table(facts), brief.figures_table(facts), _dates_table(facts)):
        if block:
            parts.append(block)
    sections = _sections(text)
    if len(sections) >= 2:
        per = 2 if len(sections) > 8 else 3
        for heading, body in sections[:_n(12, length)]:
            picked = _top(_sents(body), _n(per, length))
            if picked:
                parts.append(f"### {heading}\n\n" + _bullets(picked, owner=bool(ACTION_RE.search(heading))))
    else:
        sents = _sents(text)
        picked = _top(sents, _n(8, length))
        if picked:
            parts.append("### Main points\n\n" + _bullets(picked))
    # The document's own closing section already says it; otherwise quote a summing-up sentence if there is one.
    if not any(_CLOSING.search(h) for h, _ in sections[-2:]):
        concl = extractive.conclusion(text)
        if concl and not any(brief.mentioned(concl, p) for p in parts):
            parts.append("### Conclusion\n\n" + _line(concl))
    return parts


def _bullets_mode(text, facts, length, title, **_):
    sents = _sents(text)
    parts = _head(facts, title)
    purpose = _top(sents[: max(5, len(sents) // 8)], 1)
    if purpose:
        parts.append("### Purpose\n\n" + _bullets(purpose))
    facts_rows = [f"**{f['label']}:** {f['value']}" for f in facts["fields"] if f["kind"] != "date"]
    points = [p for p in (facts["points"] or _top(sents, _n(5, length))) if p not in purpose]
    key = facts_rows + [_line(p) for p in points]
    if key:
        parts.append("### Key facts\n\n" + "\n".join(f"- {k}" for k in key[:_n(10, length)]))
    topics = facts.get("topics") or []
    if len(topics) >= 2:
        parts.append("### Topics\n\n" + "\n".join(f"- {t[:1].upper() + t[1:]}" for t in topics))
    figs = brief.figures_table(facts)
    if figs:
        parts.append(figs.replace("### Key figures", "### Numbers", 1))
    if facts["dates"]:
        parts.append("### Dates\n\n" + "\n".join(
            f"- **{d['text']}** — {brief.date_what(d)} ({brief._rel(d['days_from_today'])})" for d in facts["dates"]))
    people = [f["value"] for f in facts["fields"] if f["kind"] == "name"]
    if people:
        parts.append("### People / organisations\n\n" + "\n".join(f"- **{p}**" for p in people))
    steps = _top(_matching(sents, ACTION_RE), _n(5, length))
    extra = _extra_actions(facts["actions"], steps)
    if steps or extra:
        parts.append("### Next steps\n\n" + "\n".join([f"- {a}" for a in extra] + [f"- {_line(s, owner=True)}" for s in steps]))
    return parts


def _executive(text, facts, length, title, **_):
    sents = _sents(text)
    overview = brief.fallback_overview(facts)
    # Classify first so each sentence lands in its most specific section, then fill findings with the rest.
    decisions = _top(_matching(sents, DECISION_RE), _n(4, length))
    actions = _top(_matching(sents, ACTION_RE, set(decisions)), _n(5, length))
    risks = _top(_matching(sents, RISK_RE, set(decisions) | set(actions)), _n(4, length))
    used = set(decisions) | set(actions) | set(risks)
    findings = [p for p in (facts["points"] or _top(sents, _n(8, length)))
                if p not in used and not brief.mentioned(p, overview)]
    parts = _head(facts, title) + ["## Bottom line", overview]
    if findings:
        parts.append("### Key findings\n\n" + _bullets(findings[:_n(5, length)]))
    figs = facts.get("figures") or []
    if len(figs) >= 2:
        parts.append(brief.figures_table({**facts, "figures": figs[:_n(5, length)]}))
    parts.append("### Decisions / Recommendations\n\n" + (_bullets(decisions) if decisions else "- None stated in the document."))
    risk_lines = [a for a in facts["actions"] if "<u>" in a]
    parts.append("### Risks & concerns\n\n" + ("\n".join(f"- {r}" for r in risk_lines) + ("\n" if risk_lines and risks else "")
                                              + _bullets(risks) if (risks or risk_lines) else "- None stated in the document."))
    if actions:
        parts.append("### Action items\n\n" + _bullets(actions, checkbox=True))
    if facts["dates"]:
        parts.append("### Important dates\n\n| Date | What |\n|---|---|\n" +
                     "\n".join(f"| **{d['text']}** | {brief._cell(brief.date_what(d))} |" for d in facts["dates"]))
    return parts


def _dates_mode(text, facts, length, title, insights=None, **_):
    parts = _head(facts, title)
    roles = {d["iso"]: d["what"] for d in facts["dates"]}
    details = {d["iso"]: d["detail"] for d in facts["dates"] if d.get("detail")}
    kinds = {"expiry": "Expiry", "deadline": "Deadline", "review": "Review / meeting", "issue": "Issue / start",
             "birth": "Birth", "mentioned": "Other"}
    rows, critical, upcoming = [], [], 0
    for d in (insights or {}).get("dates", []):
        days = (date.fromisoformat(d["iso"]) - date.today()).days
        upcoming += days >= 0
        what = d["context"].replace("|", "/")[:140]
        kind = roles.get(d["iso"]) or kinds.get(d["label"], "Other")
        when = brief._rel(days)
        rows.append(f"| **{d['text']}** | {what} | {kind} | {when} |")
        if d["label"] in {"expiry", "deadline"} or d["iso"] in roles and roles[d["iso"]] in {"Due", "Renewal due", "Expires / valid till"}:
            note = f"<u>{when}</u>" if days < 0 or days <= 30 else when
            detail = f": {details[d['iso']]}" if d["iso"] in details else ""
            critical.append(f"- **{d['text']}** — {kind} ({note}){detail}")
    if not rows:
        parts.append("No dates were found in this document.")
        return parts
    parts.append(f"**{len(rows)}** date(s) found, in chronological order — **{upcoming}** still ahead.")
    if critical:
        parts.append("### Critical deadlines\n\n" + "\n".join(dict.fromkeys(critical)))
    parts.append("### All dates\n\n| Date | Event / what happens | Type | When |\n|---|---|---|---|\n" + "\n".join(rows))
    return parts


def _actions_mode(text, facts, length, title, **_):
    sents = _matching(_sents(text), ACTION_RE)
    picked = _top(sents, _n(12, length))
    parts = _head(facts, title)
    high = _extra_actions(facts["actions"], picked)
    groups = {"High priority": [], "Medium priority": [], "Low priority": []}
    for s in picked:
        soon = any((parse_date(m.group(0))[0] or date.max) <= date.today().replace(year=date.today().year + 1)
                   for m in DATE_RE.finditer(s))
        key = "High priority" if HIGH_RE.search(s) or soon else "Medium priority" if MEDIUM_RE.search(s) else "Low priority"
        groups[key].append(s)
    if high:
        parts.append("### Urgent\n\n" + "\n".join(f"- [ ] {a}" for a in high))
    for name, items in groups.items():
        if items:
            parts.append(f"### {name}\n\n" + _bullets(items, checkbox=True))
    if len(parts) == len(_head(facts, title)):
        parts.append("No tasks or obligations were found in this document.")
    else:
        parts.append("### Notes\n\n- Tasks are taken word-for-word from the document; the owner is in bold and "
                     "priority is based on wording (must / shall / will) and dates.")
    return parts


def _simple(text, facts, length, title, **_):
    parts = _head(facts, title) + ["## In one line", brief.fallback_overview(facts).split(". ")[0].rstrip(".") + "."]
    pts = facts["points"] or _top(_sents(text), _n(5, length))
    short = []
    for s in pts[:_n(5, length)]:
        s = re.sub(r"\s*\([^)]*\)", "", s)                       # drop brackets
        words = s.split()
        short.append(" ".join(words[:28]) + ("…" if len(words) > 28 else ""))
    if short:
        parts.append("### What it means for you\n\n" + _bullets(short))
    remember = list(facts["actions"])
    remember += [f"**{d['what']}:** **{d['text']}**" for d in facts["dates"] if d["role"] in
                 {"expiry_date", "due_date", "renewal_date", "issue_date"}]
    remember += [f"**{f['label']}:** {f['value']}" for f in facts["fields"] if f["kind"] in {"amount", "id"}][:4]
    if remember:
        parts.append("### Things to remember\n\n" + "\n".join(f"- {r}" for r in dict.fromkeys(remember)))
    return parts


def _study(text, facts, length, title, **_):
    sents = _sents(text)
    parts = _head(facts, title)
    concepts = []
    for kw in _keywords(text, _n(8, length)):
        definition = next((s for s in sents if re.search(rf"\b{re.escape(kw)}\b", s, re.I)), None)
        if definition:
            concepts.append(f"- **{kw}** — {_bold_facts(definition)}")
    if concepts:
        parts.append("## Core concepts\n\n" + "\n".join(concepts))
    figures = [f"**{f['label']}:** {f['value']}" for f in facts["fields"]]
    figures += [_bold_facts(s) for s in _top([s for s in sents if re.search(r"\d", s)], _n(5, length))]
    if figures:
        parts.append("### Important facts & figures\n\n" + "\n".join(f"- {x}" for x in figures))
    quiz = []
    for s in _top(sents, 12) + [f"{f['label']} is {f['value']}." for f in facts["fields"]]:
        m = DATE_RE.search(s) or AMOUNT_RE.search(s) or PERCENT_RE.search(s)
        answer = m.group(0).strip() if m else None
        if not answer:
            kws = [k for k in _keywords(text, 15) if re.search(rf"\b{re.escape(k)}\b", s)]
            answer = kws[0] if kws else None
        if answer:
            q = s.replace(answer, "_____", 1)
            quiz.append(f"**Q{len(quiz) + 1}. Fill in the blank:** {q}\n\nAnswer: **{answer}**")
        if len(quiz) >= 5:
            break
    if quiz:
        parts.append("### Quick quiz\n\n" + "\n\n".join(quiz))
    return parts


def _custom(text, facts, length, title, instructions="", **_):
    parts = _head(facts, title)
    terms = {w.lower()[:6] for w in re.findall(r"[A-Za-z]{3,}", instructions) if w.lower() not in extractive.STOPWORDS
             and w.lower() not in {"summary", "summarise", "summarize", "write", "give", "list", "show", "explain",
                                   "document", "please", "about", "points", "short", "detail", "detailed"}}
    sents = _sents(text)
    if terms:
        scored = sorted(((sum(1 for w in re.findall(r"[a-z]{3,}", s.lower()) if w[:6] in terms), i, s)
                         for i, s in enumerate(sents)), key=lambda t: (-t[0], t[1]))
        hits = [s for score, _, s in scored if score > 0][:_n(8, length)]
    else:
        hits = []
    parts.append(f"> Matching your request: *{instructions.strip()[:200]}*")
    if hits:
        parts.append("### Most relevant lines\n\n" + _bullets(hits))
    else:
        parts.append(brief.fallback_overview(facts))
        pts = facts["points"] or _top(sents, _n(5, length))
        if pts:
            parts.append("### Key points\n\n" + _bullets(pts))
    for block in (_details_table(facts), _dates_table(facts)):
        if block:
            parts.append(block)
    return parts


STYLES = {"short": _short, "detailed": _detailed, "bullets": _bullets_mode, "executive": _executive,
          "dates": _dates_mode, "actions": _actions_mode, "simple": _simple, "study": _study, "custom": _custom}


def summarize(text: str, insights: dict, *, mode: str = "smart", length: str = "standard", instructions: str = "",
              title: str = "") -> str:
    table = tabular.parse(text)
    if table:
        return tabular.summarize(table, mode=mode, length=length, title=title, instructions=instructions)
    if mode not in STYLES:
        facts = brief.collect(text, insights, length=length)
        return brief.compose(facts, brief.fallback_overview(facts), title)
    facts = brief.collect(text, insights, length=length)
    parts = STYLES[mode](text, facts, length, title, insights=insights, instructions=instructions)
    return "\n\n".join(p for p in parts if p)


# ------------------------------------------------------------------ Q&A
INTENTS = [
    (r"expir|valid|validity|renew|kab tak|till when|until when", ["expiry_date", "renewal_date"]),
    (r"issue|jari|issued", ["issue_date"]),
    (r"birth|dob|janam|age|umar", ["dob"]),
    (r"father|pita|papa|guardian|s/o|husband|pati", ["relation"]),
    (r"mother|mata|maa", ["mother"]),
    (r"address|pata|rehta|resid|location|kahan", ["address"]),
    (r"\bdue\b|last date|deadline|pay by", ["due_date"]),
    (r"total|amount|price|fee|cost|kitna|paisa|rakam|rupee|rs\b|payable|premium|salary", ["total", "premium", "sum_insured", "salary", "tax"]),
    (r"number|\bno\b|id\b|licen[cs]e no|policy no|invoice no|nambar", None),  # any identifier
    (r"name|naam|holder|kiska|whose|who", ["name", "billed_to"]),
    (r"class|vehicle|gaadi|gadi", ["vehicle_class"]),
    (r"blood", ["blood_group"]),
    (r"created|creation|banaya|prepared", ["created_date", "doc_date"]),
]


INTENT_WORDS = {"what", "kya", "hai", "kab", "kitna", "kitni", "batao", "the", "document", "this", "mein", "ka", "ki",
                "ke", "when", "date", "dates", "how", "much", "many", "amount", "which", "where", "tell", "about",
                "does", "show", "give", "deadline", "tarikh", "kaun", "kon", "hain"}


def answer(text: str, question: str, insights: dict) -> str:
    table = tabular.parse(text)
    if table:
        return tabular.answer(table, question)
    facts = brief.collect(text, insights)
    q = question.lower()
    lines = []
    if re.search(r"\b(status|expired|active|chalu|valid hai)\b", q) and facts["expiry"]:
        lines.append(brief._status_line(facts["expiry"]).lstrip("> "))
    for pattern, keys in INTENTS:
        if not re.search(pattern, q):
            continue
        matched = [f for f in facts["fields"] if (f["kind"] == "id" if keys is None else f["key"] in keys)]
        for f in matched:
            extra = ""
            if f.get("iso"):
                extra = f" ({brief._rel((date.fromisoformat(f['iso']) - date.today()).days)})"
            lines.append(f"**{f['label']}:** **{f['value']}**{extra}")
        if matched:
            break

    # Supporting lines by topic words (prefix match tolerates plurals and Hinglish endings).
    terms = {w[:5] for w in re.findall(r"[a-z0-9]{3,}", q) if w not in extractive.STOPWORDS and w not in INTENT_WORDS}
    sents = _sents(text) or [s for s in text.splitlines() if s.strip()]
    scored = sorted(((sum(1 for w in set(re.findall(r"[a-z0-9]{3,}", s.lower())) if w[:5] in terms), i, s)
                     for i, s in enumerate(sents)), key=lambda t: (-t[0], t[1]))
    best = scored[0][0] if scored else 0
    quotes = [s for score, _, s in scored if score > 0 and score >= best - 1][:3]

    if not lines and not quotes:
        if re.search(r"\b(date|dates|kab|when|tarikh|deadline)\b", q) and facts["dates"]:
            lines += [f"**{d['what']}:** **{d['text']}** ({brief._rel(d['days_from_today'])})" for d in facts["dates"]]
        elif re.search(r"\b(amount|kitna|kitni|total|price|cost|paisa|rakam)\b", q) and facts["amounts"]:
            lines.append("**Amounts mentioned:** " + ", ".join(f"**{a}**" for a in facts["amounts"]))
        else:
            lines.append(brief.fallback_overview(facts))
            if not re.search(r"\b(summary|summarise|summarize|about|overview|explain|batao)\b", q):
                lines.insert(0, "I could not find an exact answer in the document. Here is what it says overall:")
    out = "\n\n".join(lines)
    if quotes:
        out += "\n\nFrom the document:\n\n" if out else ""
        out += "\n\n".join(f"> {_bold_facts(s)}" for s in quotes)
    return out
