"""Instant, model-free NLP: sentence splitting, key sentences, key phrases and fact context.

Key sentences combine TextRank (sentence-similarity PageRank) with word-frequency centrality and
document cues (dates, amounts, obligation words, position). Key phrases use RAKE-style scoring.
Everything returns text copied from the source, so it can be shown as-is and never invents facts.
Used for the "Key points" of every summary and to shrink long documents before a small CPU model.
"""

import math
import re
from collections import Counter, defaultdict

from services.insights import AMOUNT_RE, DATE_RE, PERCENT_RE

STOPWORDS = set("""
a about above after again against all am an and any are as at be because been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers herself him
himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other
our ours ourselves out over own same she should so some such than that the their theirs them themselves then there
these they this those through to too under until up very was we were what when where which while who whom why will
with would you your yours yourself yourselves also may shall must per via etc ie eg hereby herein thereof
""".split())

# Words that make poor topics on their own: frequent in every document, say nothing about this one.
WEAK_TOPIC = set("""
new first last next previous current overall however total number part parts time times year years month months day
days week weeks one two three four five many much several various certain following within without given made make
makes get got well like way ways use used using page pages document documents section sections item items thing things
yet still even already today also less least lot lots able unable mainly largely mostly especially particular per cent
percent rs inr usd lakh lakhs crore crores rupees dollars please dear sir madam regards sincerely quarter quarters
team teams company companies organisation organization department management people person members group staff
increase increases increased decrease decreased rise rose higher lower good better strong large small big
january february march april may june july august september october november december
""".split())

CUE_RE = re.compile(
    r"\b(must|shall|required|mandatory|deadline|due|expire\w*|valid\w*|renew\w*|penalty|fine|important|note|"
    r"total|payable|liable|terminate\w*|obligat\w*|responsib\w*|agree\w*|decid\w*|recommend\w*|conclu\w*|result\w*|"
    r"key|critical|warning|risk|approve\w*|reject\w*|summary|purpose|objective|increase\w*|decrease\w*|grew|growth|"
    r"declin\w*|revenue|profit|loss)\b",
    re.IGNORECASE,
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_ABBREV = re.compile(r"\b(?:rs|no|nos|mr|mrs|ms|dr|st|sr|jr|vs|vill|distt|dist|p\.o|po|teh|govt|dept|ltd|pvt|inc|co|"
                     r"approx|fig|ref|sec|art|cl|e\.g|i\.e|etc|[a-z])\.$", re.IGNORECASE)
# "- item", "• item", "1. item", "a) item", "(ii) item" — list markers in front of real text
_BULLET = re.compile(r"^\s*(?:[-–•*·▪●○◦►✓✔]+|\(?(?:\d{1,2}|[a-z]|[ivx]{1,4})[.)])\s+(?=\S)", re.IGNORECASE)
_PRONOUN_START = re.compile(r"^(it|this|that|these|those|they|he|she|its|their|such|both|above|below)\b", re.I)
_CONCLUSION_CUE = re.compile(r"\b(overall|in conclusion|to conclude|in summary|to sum up|therefore|thus|hence|"
                             r"in short|all in all|on the whole)\b", re.I)
ACRONYMS = {"GST", "GSTIN", "PAN", "HR", "IT", "CEO", "CFO", "CTO", "KYC", "UID", "ID", "USA", "UK", "EU", "AI", "ML",
            "API", "UI", "MOU", "NDA", "RFP", "SOP", "KPI", "ROI", "FY", "Q1", "Q2", "Q3", "Q4", "MD", "VP", "NOC"}
_SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "via", "with"}


# ------------------------------------------------------------------ sentences
def _split(part: str) -> list[str]:
    out = []
    for piece in _SENT_SPLIT.split(part):
        piece = piece.strip()
        if not piece:
            continue
        if out and (_ABBREV.search(out[-1]) or piece[0].isdigit()):
            out[-1] += " " + piece  # "Rs. 50,000", "No. 12", "P.O. Shogi" are not sentence ends
        else:
            out.append(piece)
    return out


def strip_bullet(s: str) -> str:
    return _BULLET.sub("", s, count=1).strip()


def sentences(text: str) -> list[str]:
    out = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        buf = []

        def flush():
            if buf:
                out.extend(_split(" ".join(buf)))
                buf.clear()

        for raw in (x.strip() for x in block.splitlines()):
            if not raw:
                continue
            ln = raw
            if _BULLET.match(raw) and not is_heading(raw):
                flush()  # a list item starts a new unit; wrapped continuation lines join it below
                ln = strip_bullet(raw)
                if len(ln.split()) > 8 or ln.endswith((".", ",", ";")):
                    buf.append(ln)
                    continue
            # Headings, labels and short list lines stand alone; long lines are hard-wrapped prose.
            if (len(ln.split()) <= 8 and not ln.endswith((".", ",", ";"))) or is_heading(ln) or "|" in ln:
                flush()
                out.append(ln)
            else:
                buf.append(ln)
        flush()
    return out


def is_heading(s: str) -> bool:
    """ALL-CAPS headings, and Title Case lines without sentence punctuation ("Solar Energy Adoption in India")."""
    if len(s) > 150:
        return False
    words = s.split()
    if len(words) > 12:
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    if sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return True
    return is_title_line(s)


def is_title_line(s: str) -> bool:
    words = [w.strip("()[]\"'–—-") for w in s.split()]
    words = [w for w in words if w]
    return (2 <= len(words) <= 12 and not s.rstrip().endswith((".", ",", ";", ":", "!", "?"))
            and all(w[0].isupper() or w[0].isdigit() or w.lower() in _SMALL for w in words)
            and words[0][0].isupper())


def _is_caps(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def is_label_line(s: str) -> bool:
    """"Attendees: A, B" / "Name: X" style lines are data, not sentences."""
    return re.match(r"^[\w/'()&. -]{1,30}:\s", s) is not None


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z0-9'-]+", s.lower()) if w not in STOPWORDS and len(w) > 2]


# ------------------------------------------------------------------ ranking
def _textrank(word_sets: list[set], iterations: int = 30, damping: float = 0.85) -> list[float]:
    """PageRank over a sentence graph whose edges are word overlap / (log|a| + log|b|) (Mihalcea & Tarau)."""
    n = len(word_sets)
    if n < 3:
        return [1.0] * n
    postings = defaultdict(list)
    for i, ws in enumerate(word_sets):
        for w in ws:
            postings[w].append(i)
    overlap = Counter()
    for ids in postings.values():
        if len(ids) > max(40, n // 4):  # near-universal words connect everything and only add cost
            continue
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                overlap[(ids[a], ids[b])] += 1
    logs = [math.log(len(ws) + 1) for ws in word_sets]
    edges = defaultdict(list)
    out_weight = [0.0] * n
    for (i, j), c in overlap.items():
        w = c / (logs[i] + logs[j])
        edges[i].append((j, w))
        edges[j].append((i, w))
        out_weight[i] += w
        out_weight[j] += w
    rank = [1.0] * n
    for _ in range(iterations):
        rank = [(1 - damping) + damping * sum(rank[j] * w / out_weight[j] for j, w in edges[i] if out_weight[j])
                for i in range(n)]
    return rank


def key_sentences(text: str, limit: int = 6, min_words: int = 7, max_words: int = 60) -> list[str]:
    """The `limit` most central, informative sentences, in document order and without near-duplicates."""
    sents = sentences(text)
    candidates = []
    for i, s in enumerate(sents):
        n = len(s.split())
        if not (min_words <= n <= max_words) or "|" in s or s.count(":") > 2 or is_heading(s) or is_label_line(s):
            continue
        ws = _words(s)
        if len(ws) < 3:
            continue
        lead = i > 0 and (is_heading(sents[i - 1]) or sents[i - 1].endswith(":"))
        candidates.append((i, s, ws, lead))
    if not candidates:
        return []
    candidates = candidates[:1500]
    freq = Counter(w for _, _, ws, _ in candidates for w in set(ws))
    top = max(freq.values())
    central = [sum(freq[w] / top for w in set(ws)) / len(set(ws)) for _, _, ws, _ in candidates]
    rank = _textrank([set(ws) for _, _, ws, _ in candidates]) if len(candidates) <= 400 else central
    c_max, r_max = max(central) or 1, max(rank) or 1
    opening = max(2, len(candidates) * 0.12)

    scored = []
    for k, ((i, s, ws, lead), c, r) in enumerate(zip(candidates, central, rank)):
        uniq = set(ws)
        score = 0.5 * c / c_max + 0.5 * r / r_max + 0.05 * math.log(len(uniq))
        if DATE_RE.search(s):
            score += 0.25
        if AMOUNT_RE.search(s) or PERCENT_RE.search(s):
            score += 0.25
        score += 0.12 * min(3, len(CUE_RE.findall(s)))
        if k < opening:
            score += 0.2  # openings usually state the purpose
        if lead:
            score += 0.1  # first sentence of a section states its topic
        if _PRONOUN_START.match(s):
            score -= 0.15  # "It was…" needs the previous sentence to make sense
        scored.append((score, i, s, uniq))
    scored.sort(key=lambda t: -t[0])

    chosen = []
    for score, i, s, ws in scored:
        if any(len(ws & other) / max(1, len(ws | other)) > 0.5 for _, _, other in chosen):
            continue
        chosen.append((i, s, ws))
        if len(chosen) >= limit:
            break
    return [s for _, s, _ in sorted(chosen)]


def condense(text: str, budget: int) -> str:
    """Shrink text to about `budget` characters by keeping the highest-scoring sentences in order."""
    if len(text) <= budget:
        return text
    count = max(8, budget // 160)
    picked = key_sentences(text, limit=count, min_words=5, max_words=90)
    out = "\n".join(picked)
    return out[:budget] if out else text[:budget]


def conclusion(text: str) -> str:
    """A closing sentence that sums the document up, if the text has one."""
    sents = [s for s in sentences(text) if len(s.split()) >= 7 and not is_heading(s) and not is_label_line(s)]
    tail = sents[-max(4, len(sents) // 5):]
    cued = [s for s in tail if _CONCLUSION_CUE.search(s)]
    return cued[-1] if cued else ""


# ------------------------------------------------------------------ key phrases
def keyphrases(text: str, limit: int = 6) -> list[str]:
    """RAKE-style key phrases (1-3 words) that recur in the document, most important first."""
    phrases = []
    for s in sentences(text):
        if is_heading(s) or is_label_line(s):
            continue
        for chunk in re.split(r"[^A-Za-z'\- ]+", s):
            current = []
            for w in chunk.split():
                lw = w.lower().strip("'-")
                if lw in STOPWORDS or lw in WEAK_TOPIC or len(lw) < 3 or not lw.isalpha() and "-" not in lw:
                    if current:
                        phrases.append(current)
                    current = []
                else:
                    current.append(w.strip("'-"))
            if current:
                phrases.append(current)
    phrases = [p for p in phrases if len(p) <= 3]
    freq, degree = Counter(), Counter()
    for p in phrases:
        for w in p:
            freq[w.lower()] += 1
            degree[w.lower()] += len(p)
    counts = Counter(" ".join(w.lower() for w in p) for p in phrases)
    forms = defaultdict(Counter)
    for p in phrases:
        forms[" ".join(w.lower() for w in p)][" ".join(p)] += 1

    # How often each phrase occurs, also inside longer phrases ("mobile app" in "mobile app team").
    contained = Counter()
    for key, count in counts.items():
        ws = key.split()
        for size in range(1, len(ws) + 1):
            for start in range(len(ws) - size + 1):
                contained[" ".join(ws[start:start + size])] += count

    scored = []
    for key, count in counts.items():
        ws = key.split()
        if (len(ws) == 1 and count < 3) or (count < 2 and not (len(ws) > 1 and all(freq[w] >= 2 for w in ws))):
            continue
        if len(ws) > 1 and any(contained[" ".join(ws[a:b])] > count and (b - a > 1 or freq[ws[a]] >= 3)
                               for a in range(len(ws)) for b in range(a + 1, len(ws) + 1) if b - a < len(ws)):
            continue  # a shorter phrase inside this one recurs more: that is the real topic
        n = contained[key]
        score = sum(degree[w] / freq[w] for w in ws) * (1 + math.log(n)) + 0.5 * sum(freq[w] for w in ws) / len(ws)
        scored.append((score, key))
    for key, n in contained.items():  # sub-phrases that only ever occur inside longer ones
        ws = key.split()
        if key not in counts and (n >= 2 if len(ws) > 1 else n >= 3):
            scored.append((sum(degree[w] / freq[w] for w in ws) * (1 + math.log(n)), key))
    scored.sort(key=lambda t: -t[0])

    lower_seen = set(re.findall(r"\b[a-z][a-z'-]+\b", text))
    out, used = [], []
    for _, key in scored:
        if any(key in u or u in key for u in used):
            continue
        variants = forms[key]
        if not variants:  # a sub-phrase: read how the text writes it
            for m in re.finditer(r"\b" + r"\s+".join(map(re.escape, key.split())) + r"\b", text, re.I):
                variants[" ".join(m.group(0).split())] += 1
            if not variants:
                variants[key] += 1
        lower = next((v for v in variants if v == key), None)
        surface = lower or " ".join(w.lower() if w.lower() in lower_seen else w
                                    for w in variants.most_common(1)[0][0].split())  # "Logistics" at a sentence start
        used.append(key)
        out.append(surface)
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ fact context
_CLAUSE_BREAK = re.compile(r"\s*(?:[;:()]|,(?!\d{3})|\s[-–—]\s)\s*")
_LEAD_JUNK = re.compile(r"^(?:and|but|or|which|that|who|while|whereas|with|of|by|on|at|to|for|from|in|is|was|are|"
                        r"were|approximately|about|around|nearly)\s+", re.I)
_BEFORE_VALUE = (r"(?:\b(?:(?:of\s+)?up\s+to|of|by|at|to|is|was|are|were|about|around|nearly|approximately|worth|"
                 r"totall?ing|on|dated|till|until|upto|before)\s+)?")
_TAIL_JUNK = re.compile(r"\s+(?:of|by|on|at|to|for|from|in|is|was|are|were|be|till|until|upto|before|after|dated|"
                        r"approximately|about|around|nearly|worth|totalling|totaling|the|an|a|and|or)$", re.I)


def context(sentence: str, value: str, max_words: int = 14) -> str:
    """What a date or figure in `sentence` refers to: its clause, with the value itself taken out."""
    pos = sentence.find(value)
    if pos < 0 or is_label_line(sentence):
        return ""
    clauses, start = [], 0
    for m in _CLAUSE_BREAK.finditer(sentence):
        clauses.append((start, m.start()))
        start = m.end()
    clauses.append((start, len(sentence)))
    idx = next((k for k, (a, b) in enumerate(clauses) if a <= pos < b), 0)
    a, b = clauses[idx]
    left, sep, _right = sentence[a:b].partition(" and ")
    if sep and value in left and len(left.split()) >= 4:
        b = a + len(left)  # "sales grew 24% and crossed…" -> "sales grew"

    def clean(seg: str) -> str:
        # Take the value out together with the preposition in front of it ("rose by 11% because" -> "rose because").
        seg = re.sub(_BEFORE_VALUE + re.escape(value), " ", seg, count=1, flags=re.I)
        seg = " ".join(seg.split()).strip(" .,;:-–—")
        for _ in range(3):
            seg = _LEAD_JUNK.sub("", _TAIL_JUNK.sub("", seg)).strip(" .,;:-–—")
        return seg

    seg = clean(sentence[a:b])
    if len(seg.split()) < 3 and idx > 0:  # "…, which expire on 31/12/2026" -> include what "which" refers to
        seg = clean(sentence[clauses[idx - 1][0]:b])
    if len(seg.split()) < 2:
        seg = clean(sentence)
    words = seg.split()
    if len(words) > max_words:
        seg = " ".join(words[:max_words]) + "…"
    return seg[:1].upper() + seg[1:] if seg else ""


def figures(text: str, limit: int = 6) -> list[tuple[str, str]]:
    """(amount or percentage, what it refers to) for the most informative figures, in document order."""
    found, seen = [], set()
    for s in sentences(text):
        if is_heading(s) or is_label_line(s) or "|" in s:
            continue
        matches = sorted([m for rx in (AMOUNT_RE, PERCENT_RE) for m in rx.finditer(s)], key=lambda m: m.start())
        for m in matches:
            value = m.group(0).strip().rstrip(",.")
            key = re.sub(r"\s", "", value.lower())
            if key in seen:
                continue
            what = context(s, value)
            if len(what.split()) >= 2:
                seen.add(key)
                found.append((value, what))
    if len(found) <= limit:
        return found
    # Keep amounts over percentages when space is short; keep reading order.
    ranked = sorted(range(len(found)), key=lambda k: (not AMOUNT_RE.search(found[k][0]), k))[:limit]
    return [found[k] for k in sorted(ranked)]


# ------------------------------------------------------------------ presentation
def title_case(s: str) -> str:
    """"QUARTERLY OPERATIONS REPORT – Q3 2026" -> "Quarterly Operations Report – Q3 2026"."""
    if not _is_caps(s):
        return s
    out = []
    for k, w in enumerate(s.split()):
        core = w.strip("()[]\"'.,:;")
        if re.search(r"\d", w) or core in ACRONYMS:
            out.append(w)
        elif k and w.lower() in _SMALL:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)


def doc_title(text: str) -> str:
    """The document's own title line, if it opens with one."""
    seen = 0
    for raw in text.splitlines():
        s = raw.strip().strip("#*=_ ").strip()
        if not s:
            continue
        seen += 1
        if seen > 5:
            break
        if is_label_line(s) or DATE_RE.fullmatch(s) or _BULLET.match(s):
            continue
        n = len(s.split())
        if 2 <= n <= 14 and len(s) <= 100 and not s.endswith((".", ",", ";", ":")) and (
                is_heading(s) or raw.lstrip().startswith("#") or s.istitle()):
            return title_case(s)
    return ""


def tidy(s: str) -> str:
    """A source sentence ready to show as a bullet: no list marker, capitalised, properly ended."""
    s = " ".join(strip_bullet(s).split())
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    if s and s[-1] not in ".!?:…)\"'*":
        s += "."
    return s


def bold_facts(s: str) -> str:
    """Bold dates, amounts and percentages inside a source sentence."""
    spans = sorted({(m.start(), m.end()) for rx in (DATE_RE, AMOUNT_RE, PERCENT_RE) for m in rx.finditer(s)})
    out, last = [], 0
    for a, b in spans:
        if a < last:
            continue
        if s[max(0, a - 2):a] == "**":  # already bold
            continue
        val = s[a:b].rstrip()
        trail = val[len(val.rstrip(",.")):]  # "Rs. 78,000," -> bold "Rs. 78,000", keep the comma outside
        val = val.rstrip(",.")
        out.append(s[last:a] + "**" + val.strip() + "**" + trail + (" " if s[a:b].endswith(" ") else ""))
        last = b
    return "".join(out) + s[last:]


_MODAL = re.compile(r"\b(must|shall|should|will|needs? to|has to|have to|(?:is|are) (?:required|expected) to|"
                    r"(?:is|are) to)\b", re.I)


def bold_owner(s: str) -> str:
    """"Anil must submit…" -> "**Anil** must submit…" so the owner of a task stands out."""
    m = _MODAL.search(s)
    if not m or m.start() == 0 or s.startswith("**"):
        return s
    subject = s[:m.start()].strip()
    if (1 <= len(subject.split()) <= 5 and subject[0].isupper() and not re.search(r"[,;:*\d]", subject)
            and not _PRONOUN_START.match(subject) and not re.match(r"(if|when|there|we|you|i|please)\b", subject, re.I)):
        return f"**{subject}** {s[m.start():]}"
    return s
