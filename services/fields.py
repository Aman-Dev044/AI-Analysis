"""Labelled key fields ("Name: X", "Valid Till 20/10/2026", "Policy No. AB12") read straight from the text.

Works on typed documents and on OCR output, where a value is often on the line after its label
or the colon is missing. Every value is copied from the source, so nothing here can be invented.
"""

import difflib
import re
from datetime import date
from typing import Optional

from services import id_numbers
from services.insights import DATE_RE, AMOUNT_RE, parse_date

# (key, display label, kind, label synonyms). Longer synonyms win over shorter ones ("Father's Name" vs "Name").
FIELDS = [
    # dates
    ("issue_date", "Issue date", "date", ["date of issue", "issue date", "issued on", "date of issuance", "doi", "issued date", "date issued"]),
    ("valid_from", "Valid from", "date", ["valid from", "effective from", "effective date", "start date", "commencement date",
                                          "policy start date", "period from", "date of commencement"]),
    ("expiry_date", "Valid till / Expiry", "date", ["valid till", "valid until", "valid upto", "valid up to", "valid thru", "valid through",
                                                    "validity (nt)", "validity(nt)", "validity (tr)", "validity(tr)", "validity",
                                                    "date of expiry", "expiry date", "expiration date", "expires on", "expiry", "doe",
                                                    "policy end date", "end date", "valid to"]),
    ("renewal_date", "Renewal due", "date", ["renewal date", "renewal due date", "due for renewal", "renew by", "next renewal",
                                             "renewal due"]),
    ("created_date", "Date of creation", "date", ["date of creation", "creation date", "created on", "created date", "prepared on",
                                                  "date of preparation", "generated on"]),
    ("doc_date", "Document date", "date", ["invoice date", "bill date", "receipt date", "statement date", "dated", "date"]),
    ("due_date", "Due date", "date", ["payment due date", "due date", "last date", "pay by", "payment due"]),
    ("dob", "Date of birth", "date", ["date of birth", "birth date", "dob", "d.o.b"]),
    ("joining_date", "Joining date", "date", ["date of joining", "joining date", "doj"]),
    # identifiers
    ("licence_no", "Licence no.", "id", ["driving licence no", "driving license no", "licence number", "license number", "licence no",
                                         "license no", "dl no", "dl number"]),
    ("policy_no", "Policy no.", "id", ["policy number", "policy no"]),
    ("invoice_no", "Invoice no.", "id", ["invoice number", "invoice no", "bill number", "bill no"]),
    ("receipt_no", "Receipt no.", "id", ["receipt number", "receipt no", "transaction id", "txn id", "utr"]),
    ("certificate_no", "Certificate no.", "id", ["certificate number", "certificate no", "cert no"]),
    ("passport_no", "Passport no.", "id", ["passport number", "passport no", "passport/ic no"]),
    ("visa_no", "Visa no.", "id", ["visa number", "visa no"]),
    ("registration_no", "Registration no.", "id", ["registration number", "registration no", "reg no", "enrolment no", "enrollment no",
                                                   "roll number", "roll no"]),
    ("account_no", "Account no.", "id", ["account number", "account no", "a/c no"]),
    ("reference_no", "Reference no.", "id", ["reference number", "reference no", "ref no", "order number", "order no",
                                             "application number", "application no", "id number", "id no", "serial no"]),
    ("pan", "PAN", "id", ["permanent account number", "pan number", "pan no", "pan"]),
    ("aadhaar", "Aadhaar no.", "id", ["aadhaar number", "aadhaar no", "aadhar no", "uid"]),
    ("vid", "Aadhaar VID", "id", ["vid"]),
    ("voter_id", "Voter ID (EPIC)", "id", ["epic no", "epic number", "voter id no", "voter id"]),
    ("vehicle_reg", "Vehicle no.", "id", ["vehicle registration", "vehicle registration no", "vehicle no",
                                          "vehicle number"]),
    ("national_id", "National ID", "id", ["citizenship/national id no", "national id no", "national id"]),
    ("ifsc", "IFSC", "id", ["ifsc code", "ifsc"]),
    ("gstin", "GSTIN", "id", ["gstin", "gst no", "gst number"]),
    ("employee_id", "Employee ID", "id", ["employee id", "employee code", "emp id", "emp code"]),
    # people & places
    ("surname", "Surname", "name", ["surname"]),
    ("full_name", "Name", "name", ["surname and given name(s)", "surname and given names", "surname and given name"]),
    ("given_name", "Given name(s)", "name", ["given name(s)", "given names", "given name"]),
    ("name", "Name", "name", ["name of holder", "holder's name", "holder name", "full name", "candidate name", "candidate's name",
                              "applicant name", "student name", "employee name", "customer name", "insured name",
                              "name of the insured", "policy holder", "policyholder", "name"]),
    ("relation", "Father / Guardian", "name", ["son/daughter/wife of", "s/d/w of", "s/o", "d/o", "w/o", "c/o", "father's name",
                                               "fathers name", "father name", "husband's name", "husband name", "guardian name",
                                               "guardian"]),
    ("mother", "Mother's name", "name", ["mother's name", "mothers name", "mother name"]),
    ("gender", "Gender", "text", ["gender", "sex"]),
    ("blood_group", "Blood group", "text", ["blood group"]),
    ("nationality", "Nationality", "text", ["nationality", "current nationality"]),
    ("birth_place", "Place of birth", "text", ["place of birth", "place of birth town/city"]),
    ("vehicle_class", "Vehicle class", "text", ["class of vehicle", "vehicle class", "cov"]),
    ("authority", "Issued by", "text", ["issuing authority", "licensing authority", "issued by", "place of issue"]),
    ("author", "Prepared by", "text", ["prepared by", "submitted by", "written by", "compiled by", "author"]),
    ("designation", "Designation", "text", ["designation", "position", "job title"]),
    ("course", "Course", "text", ["course", "programme", "program"]),
    ("result", "Result / Grade", "text", ["result", "cgpa", "sgpa", "grade", "division"]),
    ("billed_to", "Billed to", "text", ["billed to", "bill to", "buyer", "customer"]),
    ("seller", "Seller", "text", ["seller", "vendor", "supplier", "sold by"]),
    ("address", "Address", "text", ["permanent address", "present address", "residential address", "address", "add"]),
    # money
    ("total", "Total amount", "amount", ["grand total", "total amount", "amount payable", "net payable", "net amount",
                                         "balance due", "amount due", "total due", "total"]),
    ("sum_insured", "Sum insured", "amount", ["sum insured", "sum assured", "cover amount"]),
    ("premium", "Premium", "amount", ["total premium", "premium amount", "premium"]),
    ("tax", "Tax / GST", "amount", ["total tax", "gst amount", "igst", "cgst", "sgst", "tax amount"]),
    ("salary", "Salary / CTC", "amount", ["annual ctc", "ctc", "gross salary", "net salary", "salary"]),
]

_BY_SYNONYM = {}
for _key, _label, _kind, _syns in FIELDS:
    for _s in _syns:
        _BY_SYNONYM.setdefault(_s, _key)
_META = {key: (label, kind) for key, label, kind, _ in FIELDS}
_ORDER = {key: i for i, (key, *_rest) in enumerate(FIELDS)}

_SYN_SORTED = sorted(_BY_SYNONYM, key=len, reverse=True)
_LABEL_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(re.escape(s).replace("\\ ", " ").replace(" ", r"\s*") for s in _SYN_SORTED) + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_GENERIC_ID_RE = re.compile(
    r"(?im)^[ \t\-•*]*([A-Za-z][A-Za-z&/ ]{1,28}?)[ \t]*(?:No|Number|Num|#)\.?[ \t]*[:\-–=][ \t]*([^\n]{3,60})$")
_SEP_RE = re.compile(r"^\s*(?:[:：\-–—=|>]+|\.(?!\d))\s*")
_BULLET_RE = re.compile(r"^[\s\-•*·>\d.)(]*")

_NAME_PARTICLES = {"bin", "binti", "de", "da", "del", "van", "von", "al", "el", "ul", "ud", "s/o", "d/o", "w/o"}
_GENDER_RE = re.compile(r"\b(?:male|female|transgender)\b|(?<![A-Za-z])[MF](?![A-Za-z])", re.I)
# "हिंदी / Label", "34-A/Surname": OCR junk or another script in front of the English label.
_SCRIPT_PREFIX = re.compile(r"^[^/\n]{0,40}?/\s*")
_COMPACT_SYNS = {re.sub(r"[^a-z]", "", syn): syn for syn in _BY_SYNONYM if len(re.sub(r"[^a-z]", "", syn)) >= 6}
# OCR drops spaces inside labels ("Dateof Birth", "Father'sName"): look synonyms up without them.
_BY_COMPACT = {re.sub(r"[^a-z]", "", syn): syn for syn in _BY_SYNONYM}
# A date whose separators OCR read as a digit or letter: "26706/2017", "2710212030" (27/02/2030).
_GARBLED_DATE = re.compile(r"(?<!\d)(\d{2})[/.\-71|lI](\d{2})[/.\-71|lI](\d{4})(?!\d)")

# Synonyms that are ordinary English words: only trusted as a label with a separator or on a short line.
_WEAK = {"name", "date", "dated", "total", "result", "grade", "course", "programme", "program", "position", "address",
         "add", "customer", "buyer", "seller", "vendor", "supplier", "sex", "uid", "pan", "cov", "utr", "doe", "doi",
         "dob", "doj", "division", "guardian", "premium", "expiry", "validity", "salary", "ctc", "end date", "payment due"}


def _norm_syn(raw: str) -> str:
    syn = " ".join(raw.lower().replace("\n", " ").split())
    return syn if syn in _BY_SYNONYM else _BY_COMPACT.get(re.sub(r"[^a-z]", "", syn), syn)


def _repair_date(value: str) -> Optional[str]:
    """A date next to a date label whose separators OCR misread, as dd/mm/yyyy (only when it is a real date)."""
    for m in _GARBLED_DATE.finditer(value):
        candidate = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        if int(m.group(2)) <= 12 and parse_date(candidate)[0]:
            return candidate
    return None


def _first_cell(value: str) -> str:
    """The value's own cell: OCR keeps a column gap as 3+ spaces, and the next column is not part of it."""
    value = re.sub(r"^\s*\([^)]{0,30}\)", "", value.strip())  # "(As in Passport)": a note, not the value
    return re.split(r"\s{3,}|;", value.strip(), maxsplit=1)[0]


def _clean_value(value: str) -> str:
    value = " ".join(_first_cell(value).split())
    value = re.sub(r"^[^\w₹$€£(]+", "", value)          # leading OCR junk / punctuation
    return value.strip(" .,;:|-–—")[:140]


def _looks_like_label(line: str) -> bool:
    m = _LABEL_RE.match(_BULLET_RE.sub("", line))
    return bool(m)


def _valid(kind: str, key: str, value: str) -> Optional[str]:
    """Return the value normalised for its kind, or None when it does not fit."""
    if not value or len(value) < 2:
        return None
    if kind in {"text", "name"}:  # the next column's label ("Nationality by Birth") is not this field's value
        compact = re.sub(r"[^a-z]", "", value.lower())
        if any(compact.startswith(c) for c in _COMPACT_SYNS):
            return None
    if kind == "date":
        m = DATE_RE.search(value)
        if not m or parse_date(m.group(0))[0] is None:
            return _repair_date(value)
        return m.group(0)
    if kind == "amount":
        value = re.sub(r"\d+(?:\.\d+)?\s?%", "", value)  # a rate is not the amount
        m = AMOUNT_RE.search(value) or re.search(r"\d[\d,]*(?:\.\d+)?", value)
        return m.group(0).strip() if m else None
    if key == "gender":
        m = _GENDER_RE.search(value)
        return {"m": "Male", "f": "Female"}.get(m.group(0).lower(), m.group(0).title()) if m else None
    if kind == "id":
        if key == "pan":
            m = re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", value)
            return m.group(0) if m else None
        value = re.sub(r"^(?:[A-Za-z][A-Za-z ]{1,18}:\s*)+", "", value)  # "ISSUE: K1234567": skip a stray label
        parts = []
        for tok in value.split()[:4]:  # an ID is the leading run of code-like tokens
            if re.search(r"\d", tok) or (tok.isupper() and len(tok) <= 5) or tok in {"-", "/"}:
                parts.append(tok)
            else:
                break
        token = " ".join(parts).strip(" -/")
        if not re.search(r"\d", token) or len(token) > 40:
            return None
        return token
    if kind == "name":
        value = re.sub(r"(?:\s+\d[\d/.\-]*)+$", "", value)  # a number printed beside the name ("SINGH 13012020")
        if re.search(r"\d", value) or len(value.split()) > 6:
            return None
        letters = sum(c.isalpha() for c in value)
        if any(w[0].islower() and w not in _NAME_PARTICLES for w in value.split()):
            return None
        return value if letters >= 4 and letters / max(1, len(value.replace(" ", ""))) > 0.75 else None
    # free text: a bare date or number is another field's value, not this one's
    if len(value.split()) > 22 or (key != "result" and re.fullmatch(r"[\d\s/.,:\-]+", value)):
        return None
    return value


def _label_part(line: str) -> str:
    """The English label of a bilingual or OCR-garbled label line ("जन्म तिथि / DOB: ..."), when there is one."""
    if _LABEL_RE.match(line):
        return line
    m = _SCRIPT_PREFIX.match(line)
    if m and _LABEL_RE.match(line[m.end():]) and len(re.findall(r"[A-Za-z]{2,}", m.group(0))) <= 2:
        return line[m.end():]
    m = re.match(r"[^\x00-\x7f][^A-Za-z]*", line)  # "उपनाम और   Surname and Given Name": Hindi label first
    if m and _LABEL_RE.match(line[m.end():]):
        return line[m.end():]
    return line


def _fuzzy_label(line: str) -> Optional[str]:
    """A label-only line OCR misspelt ("Dateo Epiy", "Paceof Issue"): the synonym it is closest to."""
    if re.search(r"\d", line) or len(line.split()) > 5:
        return None
    compact = re.sub(r"[^a-z]", "", line.lower())
    if len(compact) < 6:
        return None
    best = difflib.get_close_matches(compact, _COMPACT_SYNS, n=1, cutoff=0.82)
    return _COMPACT_SYNS[best[0]] if best else None


def _date_entry(key: str, value: str, today: date, **extra) -> dict:
    parsed, ambiguous = parse_date(value)
    label, kind = _META[key]
    return {"key": key, "label": label, "value": value, "kind": kind, "iso": parsed.isoformat(),
            "ambiguous": ambiguous, "days_from_today": (parsed - today).days, **extra}


_ID_GATES = {  # numbers whose shape alone is not distinctive enough: the document must also say what it is
    "passport_no": re.compile(r"passport", re.I),
    "voter_id": re.compile(r"elector|election|epic|voter", re.I),
    "vehicle_reg": re.compile(r"vehicle|registration|\breg\b|\brc\b", re.I),
    "aadhaar": re.compile(r"aadhaa?r|आधार|uidai|government of india|\bVID\b|\d{4} \d{4} \d{4}", re.I),
    "vid": re.compile(r"\bVID\b"),
    "ifsc": re.compile(r"ifsc", re.I),
}
_NOT_A_NAME = re.compile(r"government|india|department|republic|commission|authority|card|male|female|signature"
                         r"|income|tax|account|number|date|birth|issue|expiry|name|nationality|code|place|sex", re.I)


def _verified_ids(text: str, found: dict, today: date) -> None:
    """Identity numbers recognised by format and checksum, and the passport/visa machine-readable zone.
    A checksum-verified value replaces what was read next to a label (OCR may have misread that copy)."""
    for item in id_numbers.find_ids(text):
        key = item["key"]
        gate = _ID_GATES.get(key)
        if gate and not gate.search(text):
            continue
        if key not in found or item.get("checked"):
            label, kind = _META[key]
            found[key] = {"key": key, "label": label, "value": item["value"], "kind": kind,
                          **({"verified": True} if item.get("checked") else {})}
    mrz = id_numbers.parse_mrz(text, today)
    if not mrz:
        return
    number_key = "passport_no" if mrz["document"] == "Passport" else "visa_no"
    if mrz["number"]:
        found[number_key] = {"key": number_key, "label": _META[number_key][0], "value": mrz["number"],
                             "kind": "id", "verified": True}
    for key, iso in (("dob", mrz["dob"]), ("expiry_date", mrz["expiry"])):
        if iso:
            found[key] = _date_entry(key, date.fromisoformat(iso).strftime("%d/%m/%Y"), today, verified=True)
    name = " ".join(filter(None, (mrz["given_names"], mrz["surname"])))
    if name and "name" not in found:
        found["name"] = {"key": "name", "label": "Name", "value": name, "kind": "name"}
    if mrz["sex"] and "gender" not in found:
        found["gender"] = {"key": "gender", "label": "Gender", "value": mrz["sex"], "kind": "text"}
    if mrz["nationality"] and not re.fullmatch(r"[A-Za-z ]{3,20}", found.get("nationality", {}).get("value", "")):
        found["nationality"] = {"key": "nationality", "label": "Nationality", "value": mrz["nationality"],
                                "kind": "text"}


def _old_pan_layout(lines: list[str], found: dict, today: date) -> None:
    """PAN cards before 2018: holder's name, father's name and date of birth on consecutive unlabelled lines."""
    people = [ln for ln in lines if re.fullmatch(r"[A-Z][A-Z.' ]{2,40}", ln) and 1 <= len(ln.split()) <= 4
              and not _NOT_A_NAME.search(ln)]
    if people:
        found["name"] = {"key": "name", "label": "Name", "value": people[0], "kind": "name"}
    if len(people) > 1 and "relation" not in found:
        found["relation"] = {"key": "relation", "label": _META["relation"][0], "value": people[1], "kind": "name"}
    if "dob" not in found:
        m = DATE_RE.search("\n".join(lines))
        if m and parse_date(m.group(0))[0]:
            found["dob"] = _date_entry("dob", m.group(0), today)


def _unlabelled_name(lines: list[str]) -> Optional[str]:
    """ID cards (Aadhaar) print the holder's name, without a label, on the line just above the date of birth."""
    for i, line in enumerate(lines):
        if re.search(r"\b(?:dob|d\.o\.b|date of birth|year of birth)\b", line, re.I):
            for prev in reversed(lines[max(0, i - 2):i]):
                words = prev.split()
                if 1 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", w) for w in words) \
                        and any(len(w) >= 3 for w in words) and not _NOT_A_NAME.search(prev):
                    return prev
            return None
    return None


def _date_labels(line: str) -> list[str]:
    """Date labels on one line, in order: "Date of Issue   Date of Expiry" (also when OCR misspelt them)."""
    keys = []
    for segment in re.split(r"\s*/\s*|\s{2,}", line):
        words = re.sub(r"[^\x00-\x7f]+", " ", segment).split()
        best, best_ratio = None, 0.0
        for k in range(1, min(4, len(words)) + 1):
            compact = re.sub(r"[^a-z]", "", " ".join(words[:k]).lower())
            if len(compact) < 6:
                continue
            for cand, syn in _COMPACT_SYNS.items():
                if _META[_BY_SYNONYM[syn]][1] != "date":
                    continue
                ratio = difflib.SequenceMatcher(None, compact, cand).ratio()
                if ratio > best_ratio:
                    best, best_ratio = _BY_SYNONYM[syn], ratio
        if best and best_ratio >= 0.82 and best not in keys:
            keys.append(best)
    return keys


_DATE_PATTERN = re.sub(r"\?P<\w+>", "?:", DATE_RE.pattern)  # unnamed groups: used twice below
_PERIOD_RE = re.compile(
    r"\b(?:period\s*of\s*(?:insurance|cover(?:age)?|validity)|policy\s*period|validity\s*period|valid\s*from"
    r")\b[^\n]{0,40}?(" + _DATE_PATTERN + r")\s*(?:to|till|until|upto|-|–)\s*("
    + _DATE_PATTERN + r")", re.I)


def _period(text: str, found: dict, today: date) -> None:
    """A validity period written as a range: its start is "Valid from", its end the expiry date."""
    m = _PERIOD_RE.search(text)
    if not m:
        return
    start, end = DATE_RE.search(m.group(0)), None
    for end in DATE_RE.finditer(m.group(0)):
        pass
    if start and end and start.start() != end.start():
        found.setdefault("valid_from", _date_entry("valid_from", start.group(0), today))
        found.setdefault("expiry_date", _date_entry("expiry_date", end.group(0), today))


def _paired_dates(lines: list[str], found: dict, today: date) -> None:
    """Two or more date labels on one line with their dates, in the same order, on the next line."""
    for idx, line in enumerate(lines[:-1]):
        if not line or DATE_RE.search(line) or len(line) > 160:
            continue
        keys = _date_labels(line)
        if len(keys) < 2:
            continue
        nxt = next((ln for ln in lines[idx + 1:idx + 3] if ln), "")
        values = [_valid("date", "", tok) for tok in nxt.split()]
        values = [v for v in values if v]
        if len(values) == len(keys):
            for key, value in zip(keys, values):
                found.setdefault(key, _date_entry(key, value, today))


def extract_fields(text: str, today: Optional[date] = None) -> list[dict]:
    """[{key, label, value, kind, iso?}] in a sensible reading order, one entry per key."""
    today = today or date.today()
    lines = [ln.strip() for ln in text.splitlines()]
    found: dict[str, dict] = {}
    _paired_dates(lines, found, today)
    _period(text, found, today)

    for idx, line in enumerate(lines):
        if not line or len(line) > 220:
            continue
        body = _BULLET_RE.sub("", line) if _BULLET_RE.match(line) else line
        body = _label_part(body)
        matches = list(_LABEL_RE.finditer(body))
        if not matches:
            fuzzy = _fuzzy_label(body)
            key = _BY_SYNONYM.get(fuzzy) if fuzzy else None
            if key and key not in found:  # a misspelt label line: its value is on the next line
                label, kind = _META[key]
                nxt = next((ln for ln in lines[idx + 1:idx + 3] if ln), "")
                good = _valid(kind, key, _clean_value(nxt)) if nxt and not _looks_like_label(nxt) else None
                if good:
                    found[key] = _date_entry(key, good, today) if kind == "date" else \
                        {"key": key, "label": label, "value": good, "kind": kind}
            continue
        short_line = len(body.split()) <= 9
        for n, m in enumerate(matches):
            syn = _norm_syn(m.group(1))
            key = _BY_SYNONYM.get(syn)
            if not key or key in found:
                continue
            end = matches[n + 1].start() if n + 1 < len(matches) else len(body)
            rest = body[m.end():end]
            has_sep = bool(_SEP_RE.match(rest))
            at_start = m.start() == 0
            if syn in _WEAK and not has_sep and not (at_start and short_line):
                continue
            if syn == "add" and not rest.lstrip().startswith(":"):
                continue  # "Add - On Coverages" is not an address
            if not has_sep and not at_start and not short_line:
                continue
            label, kind = _META[key]
            value = _clean_value(_SEP_RE.sub("", rest, count=1))
            good = _valid(kind, key, value)
            cells = re.split(r"\s{3,}", _SEP_RE.sub("", rest, count=1).strip())
            if not good and len(cells) > 1 and len(cells[0].split()) <= 3 \
                    and (not re.search(r"\d", cells[0]) or re.fullmatch(r"\W*\d+(?:\.\d+)?\s?%", cells[0])):
                good = _valid(kind, key, _clean_value(cells[1]))
            if not good and at_start and (kind == "date" or (n + 1 == len(matches) and (not value or short_line))):
                # value on the next non-empty line (common in OCR and two-column layouts)
                following = [ln for ln in lines[idx + 1:idx + 3] if ln]
                if kind == "date":  # a row of other text may sit between a date label and its date
                    good = next((v for v in (_valid(kind, key, _clean_value(ln)) for ln in following) if v), None)
                elif following and not _looks_like_label(_label_part(following[0])):
                    good = _valid(kind, key, _clean_value(following[0]))
            if not good:
                continue
            entry = {"key": key, "label": label, "value": good, "kind": kind}
            if kind == "date":
                parsed, ambiguous = parse_date(good)
                entry.update(iso=parsed.isoformat(), ambiguous=ambiguous, days_from_today=(parsed - today).days)
            found[key] = entry

    _verified_ids(text, found, today)
    if "name" not in found and "full_name" in found:
        found["name"] = {**found.pop("full_name"), "key": "name"}
    if "name" not in found and "given_name" in found and "surname" in found:
        found["name"] = {"key": "name", "label": "Name", "kind": "name",
                         "value": f'{found["given_name"]["value"]} {found["surname"]["value"]}'}
    if "name" not in found and "pan" in found and re.search(r"income\s*tax\s*department", text, re.I):
        _old_pan_layout(lines, found, today)
    if "name" not in found:
        name = _unlabelled_name(lines)
        if name:
            found["name"] = {"key": "name", "label": "Name", "value": name, "kind": "name"}
    if "gender" not in found:
        m = re.search(r"\b(MALE|FEMALE|Male|Female)\b", text)
        if m:
            found["gender"] = {"key": "gender", "label": "Gender", "value": m.group(1).title(), "kind": "text"}

    # A generic "Date:" that repeats the issue/creation date adds nothing.
    if "doc_date" in found and any(found.get(k, {}).get("iso") == found["doc_date"]["iso"]
                                   for k in ("issue_date", "created_date")):
        found.pop("doc_date")

    # Any other "<Something> No: X" / "<Something> Number - X" line, e.g. "Agreement No: SA-2026-77".
    known = {f["value"] for f in found.values()}
    for m in _GENERIC_ID_RE.finditer(text):
        name = " ".join(m.group(1).split())
        key = "id_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        value = _valid("id", key, _clean_value(m.group(2)))
        if value and key not in found and value not in known and len(found) < 40:
            found[key] = {"key": key, "label": f"{name.title()} no.", "value": value, "kind": "id"}
            known.add(value)
    return sorted(found.values(), key=lambda f: _ORDER.get(f["key"], _ORDER["employee_id"] + 0.5))


def key_dates(fields: list[dict], insights: dict) -> list[dict]:
    """Role-labelled important dates: labelled fields first, then labelled dates found by insights."""
    roles = {"issue_date": "Issued", "valid_from": "Valid from", "created_date": "Created", "doc_date": "Dated",
             "dob": "Date of birth", "joining_date": "Joining", "due_date": "Due", "renewal_date": "Renewal due",
             "expiry_date": "Expires / valid till"}
    out, seen = [], set()
    for f in fields:
        if f["kind"] == "date" and f["key"] in roles:
            out.append({"text": f["value"], "iso": f["iso"], "what": roles[f["key"]], "role": f["key"], "source": "field",
                        "days_from_today": f["days_from_today"], "ambiguous": f.get("ambiguous", False)})
            seen.add(f["iso"])
    label_role = {"expiry": ("Expiry / validity", "expiry_date"), "deadline": ("Deadline", "due_date"),
                  "issue": ("Issued / effective", "issue_date"), "birth": ("Date of birth", "dob"),
                  "review": ("Review / meeting", "review")}
    for d in insights.get("dates", []):
        if d["iso"] in seen or d["label"] not in label_role:
            continue
        what, role = label_role[d["label"]]
        out.append({"text": d["text"], "iso": d["iso"], "what": what, "role": role, "source": "text",
                    "days_from_today": d["days_from_today"], "ambiguous": d.get("ambiguous", False)})
        seen.add(d["iso"])
        if len(out) >= 12:
            break
    out.sort(key=lambda d: d["iso"])
    return out
