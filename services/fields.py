"""Labelled key fields ("Name: X", "Valid Till 20/10/2026", "Policy No. AB12") read straight from the text.

Works on typed documents and on OCR output, where a value is often on the line after its label
or the colon is missing. Every value is copied from the source, so nothing here can be invented.
"""

import re
from datetime import date
from typing import Optional

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
    ("passport_no", "Passport no.", "id", ["passport number", "passport no"]),
    ("registration_no", "Registration no.", "id", ["registration number", "registration no", "reg no", "enrolment no", "enrollment no",
                                                   "roll number", "roll no"]),
    ("account_no", "Account no.", "id", ["account number", "account no", "a/c no"]),
    ("reference_no", "Reference no.", "id", ["reference number", "reference no", "ref no", "order number", "order no",
                                             "application number", "application no", "id number", "id no", "serial no"]),
    ("pan", "PAN", "id", ["permanent account number", "pan number", "pan no", "pan"]),
    ("aadhaar", "Aadhaar no.", "id", ["aadhaar number", "aadhaar no", "aadhar no", "uid"]),
    ("gstin", "GSTIN", "id", ["gstin", "gst no", "gst number"]),
    ("employee_id", "Employee ID", "id", ["employee id", "employee code", "emp id", "emp code"]),
    # people & places
    ("name", "Name", "name", ["name of holder", "holder's name", "holder name", "full name", "candidate name", "candidate's name",
                              "applicant name", "student name", "employee name", "customer name", "insured name",
                              "name of the insured", "policy holder", "policyholder", "name"]),
    ("relation", "Father / Guardian", "name", ["son/daughter/wife of", "s/d/w of", "s/o", "d/o", "w/o", "c/o", "father's name",
                                               "fathers name", "father name", "husband's name", "husband name", "guardian name",
                                               "guardian"]),
    ("mother", "Mother's name", "name", ["mother's name", "mothers name", "mother name"]),
    ("gender", "Gender", "text", ["gender", "sex"]),
    ("blood_group", "Blood group", "text", ["blood group"]),
    ("nationality", "Nationality", "text", ["nationality"]),
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

# Synonyms that are ordinary English words: only trusted as a label with a separator or on a short line.
_WEAK = {"name", "date", "dated", "total", "result", "grade", "course", "programme", "program", "position", "address",
         "add", "customer", "buyer", "seller", "vendor", "supplier", "sex", "uid", "pan", "cov", "utr", "doe", "doi",
         "dob", "doj", "division", "guardian", "premium", "expiry", "validity", "salary", "ctc", "end date", "payment due"}


def _norm_syn(raw: str) -> str:
    return " ".join(raw.lower().replace("\n", " ").split())


def _clean_value(value: str) -> str:
    value = " ".join(value.split())
    value = re.sub(r"^[^\w₹$€£(]+", "", value)          # leading OCR junk / punctuation
    return value.strip(" .,;:|-–—")[:140]


def _looks_like_label(line: str) -> bool:
    m = _LABEL_RE.match(_BULLET_RE.sub("", line))
    return bool(m)


def _valid(kind: str, key: str, value: str) -> Optional[str]:
    """Return the value normalised for its kind, or None when it does not fit."""
    if not value or len(value) < 2:
        return None
    if kind == "date":
        m = DATE_RE.search(value)
        if not m or parse_date(m.group(0))[0] is None:
            return None
        return m.group(0)
    if kind == "amount":
        m = AMOUNT_RE.search(value) or re.search(r"\d[\d,]*(?:\.\d+)?", value)
        return m.group(0).strip() if m else None
    if kind == "id":
        if key == "pan":
            m = re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", value)
            return m.group(0) if m else None
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
        if re.search(r"\d", value) or len(value.split()) > 6:
            return None
        letters = sum(c.isalpha() for c in value)
        return value if letters >= 3 and letters / max(1, len(value.replace(" ", ""))) > 0.75 else None
    # free text
    if len(value.split()) > 22:
        return None
    return value


def extract_fields(text: str, today: Optional[date] = None) -> list[dict]:
    """[{key, label, value, kind, iso?}] in a sensible reading order, one entry per key."""
    today = today or date.today()
    lines = [ln.strip() for ln in text.splitlines()]
    found: dict[str, dict] = {}

    for idx, line in enumerate(lines):
        if not line or len(line) > 220:
            continue
        body = _BULLET_RE.sub("", line) if _BULLET_RE.match(line) else line
        matches = list(_LABEL_RE.finditer(body))
        if not matches:
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
            if not has_sep and not at_start and not short_line:
                continue
            label, kind = _META[key]
            value = _clean_value(_SEP_RE.sub("", rest, count=1))
            good = _valid(kind, key, value)
            if not good and n + 1 == len(matches) and (not value or short_line):
                # value on the next non-empty line (common in OCR and two-column layouts)
                nxt = next((ln for ln in lines[idx + 1:idx + 3] if ln), "")
                if nxt and not _looks_like_label(nxt):
                    good = _valid(kind, key, _clean_value(nxt))
            if not good:
                continue
            entry = {"key": key, "label": label, "value": good, "kind": kind}
            if kind == "date":
                parsed, ambiguous = parse_date(good)
                entry.update(iso=parsed.isoformat(), ambiguous=ambiguous, days_from_today=(parsed - today).days)
            found[key] = entry

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
