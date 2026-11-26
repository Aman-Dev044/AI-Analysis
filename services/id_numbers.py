"""Identity numbers recognised by their format and check digits (no model involved).

Indian IDs follow fixed patterns, several with a checksum: Aadhaar (Verhoeff), GSTIN (mod-36) and the
machine-readable zone (MRZ) of passports and visas (7-3-1 check digits). OCR often swaps look-alike
characters (O/0, I/1, S/5, B/8, Z/2), so each candidate is repaired position by position (a digit where
the format needs a digit, a letter where it needs a letter) and only kept when the format, and the
checksum where there is one, agrees. A number that passes a checksum is right, whatever OCR read.
"""

import re
from datetime import date
from typing import Optional

_TO_DIGIT = str.maketrans({"O": "0", "o": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "l": "1", "i": "1", "L": "1",
                           "|": "1", "Z": "2", "z": "2", "S": "5", "s": "5", "B": "8", "G": "6", "b": "6", "T": "7",
                           "g": "9", "q": "9", "A": "4"})
_TO_ALPHA = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "7": "T", "4": "A"})

# ------------------------------------------------------------------ checksums
_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_ok(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_ok(gstin: str) -> bool:
    total = 0
    for i, ch in enumerate(gstin[:14]):
        product = _GST_CHARS.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _GST_CHARS[(36 - total % 36) % 36] == gstin[14]


def _mrz_value(ch: str) -> int:
    if ch.isdigit():
        return int(ch)
    if "A" <= ch <= "Z":
        return ord(ch) - 55
    return 0  # "<"


def mrz_check(field: str) -> str:
    return str(sum(_mrz_value(c) * (7, 3, 1)[i % 3] for i, c in enumerate(field)) % 10)


# ------------------------------------------------------------------ helpers
def _shape(raw: str, pattern: str) -> str:
    """Force look-alike characters into the pattern: 'A' = letter, '9' = digit, anything else kept."""
    out = []
    for ch, want in zip(raw, pattern):
        if want == "9":
            out.append(ch.translate(_TO_DIGIT))
        elif want == "A":
            out.append(ch.upper().translate(_TO_ALPHA))
        else:
            out.append(ch)
    return "".join(out)


def _fits(value: str, pattern: str) -> bool:
    return len(value) == len(pattern) and all(
        (w == "9" and c.isdigit()) or (w == "A" and "A" <= c <= "Z") or (w not in "9A" and c == w)
        for c, w in zip(value, pattern))


def _add(out: list, seen: set, key: str, value: str, **extra):
    if (key, value) not in seen:
        seen.add((key, value))
        out.append({"key": key, "value": value, **extra})


# ------------------------------------------------------------------ recognisers
_PAN_HOLDER = set("PCHFATBLJGE")  # 4th character: person, company, HUF, firm, AOP, trust, BOI, LA, AJP, govt
_PAN_CAND = re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9]{5}\s?[A-Za-z0-9]{4}\s?[A-Za-z0-9])(?![A-Za-z0-9])")
# Not part of a longer digit run: the first 12 digits of a 16-digit VID are not an Aadhaar number.
_AADHAAR_CAND = re.compile(r"(?<![\dA-Za-z])(?<!\d[ \-])([2-9OISZB][\dOISZBG]{3})[ \-]?([\dOISZBG]{4})[ \-]?([\dOISZBG]{4})"
                           r"(?![\dA-Za-z])(?![ \-]\d)")
_VID_CAND = re.compile(r"(?<!\d)(\d{4})[ \-]?(\d{4})[ \-]?(\d{4})[ \-]?(\d{4})(?!\d)")
_EPIC_CAND = re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9]{3}[0-9OISZBG]{7})(?![A-Za-z0-9])")
_PASSPORT_CAND = re.compile(r"(?<![A-Za-z0-9])([A-Z][0-9OISZB]{7})(?![A-Za-z0-9])")
_GSTIN_CAND = re.compile(r"(?<![A-Za-z0-9])(\d{2}[A-Z0-9]{10}[0-9A-Z]Z[0-9A-Z])(?![A-Za-z0-9])")
_IFSC_CAND = re.compile(r"(?<![A-Za-z0-9])([A-Z]{4}[0O][A-Z0-9]{6})(?![A-Za-z0-9])")
_VEHICLE_CAND = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2})[ \-]?(\d{1,2})[ \-]?([A-Z]{0,3})[ \-]?(\d{4})(?![A-Za-z0-9])")
_STATES = set("AN AP AR AS BR CH CG DD DL DN GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD OR PB PY RJ SK TN TR TS "
              "UK UP WB BH".split())


def find_ids(text: str) -> list[dict]:
    """[{key, value, checked?}] for every identity number in the text, checksum-verified where possible."""
    out, seen = [], set()
    for m in _PAN_CAND.finditer(text):
        raw = m.group(1).replace(" ", "")
        if sum(c.isdigit() for c in raw) < 2:
            continue  # a plain word ("Department") is not a PAN
        value = _shape(raw, "AAAAA9999A")
        if _fits(value, "AAAAA9999A") and value[3] in _PAN_HOLDER:
            _add(out, seen, "pan", value)
    for m in _AADHAAR_CAND.finditer(text):
        digits = "".join(m.groups()).translate(_TO_DIGIT)
        if digits.isdigit() and verhoeff_ok(digits):
            _add(out, seen, "aadhaar", f"{digits[:4]} {digits[4:8]} {digits[8:]}", checked=True)
    for m in _VID_CAND.finditer(text):
        digits = "".join(m.groups())
        if verhoeff_ok(digits):
            _add(out, seen, "vid", " ".join(m.groups()), checked=True)
    for m in _EPIC_CAND.finditer(text):
        raw = m.group(1)
        value = _shape(raw, "AAA9999999")
        if _fits(value, "AAA9999999") and sum(c.isalpha() for c in raw[:3]) >= 2:
            _add(out, seen, "voter_id", value)
    for m in _GSTIN_CAND.finditer(text):
        if gstin_ok(m.group(1)):
            _add(out, seen, "gstin", m.group(1), checked=True)
    for m in _IFSC_CAND.finditer(text):
        _add(out, seen, "ifsc", m.group(1)[:4] + "0" + m.group(1)[5:])
    for m in _VEHICLE_CAND.finditer(text):
        state, district, series, number = m.groups()
        if state in _STATES and int(district) > 0:
            _add(out, seen, "vehicle_reg", "-".join(p for p in (state, district.zfill(2), series, number) if p))
    for m in _PASSPORT_CAND.finditer(text):
        value = _shape(m.group(1), "A9999999")
        if _fits(value, "A9999999"):
            _add(out, seen, "passport_no", value)
    return out


# ------------------------------------------------------------------ MRZ (passports, visas, ID cards)
_MRZ_JUNK = str.maketrans({"«": "<", "‹": "<", "く": "<", "〈": "<", "(": "<", "{": "<", "[": "<", " ": ""})


def _mrz_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        s = line.strip().upper().translate(_MRZ_JUNK)
        s = re.sub(r"K{3,}", lambda m: "<" * len(m.group(0)), s)  # "<<<" often comes back as "KKK"
        if len(s) >= 28 and s.count("<") >= 2 and re.fullmatch(r"[A-Z0-9<]+", s):
            lines.append(s)
    return lines


def _fix_checked(field: str, check: str, pattern: str) -> Optional[str]:
    """The field, with look-alike characters repaired, when its check digit agrees."""
    value = _shape(field, pattern)
    check = check.translate(_TO_DIGIT)
    if check.isdigit() and mrz_check(value) == check:
        return value
    return None


def _mrz_date(yymmdd: str, future: bool, today: date) -> Optional[str]:
    try:
        yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
        century = 2000 if (future or yy <= today.year % 100) else 1900
        return date(century + yy, mm, dd).isoformat()
    except ValueError:
        return None


def _mrz_name(line1: str, start: int) -> tuple[str, str]:
    parts = line1[start:].split("<<", 1)
    surname = parts[0].replace("<", " ").strip()
    given = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
    return " ".join(surname.split()).title(), " ".join(given.split()).title()


def parse_mrz(text: str, today: Optional[date] = None) -> Optional[dict]:
    """Passport (TD3) or visa (MRV-A) machine-readable zone. Only check-digit-verified values are returned."""
    today = today or date.today()
    lines = _mrz_lines(text)
    for i in range(len(lines) - 1):
        l1, l2 = lines[i], lines[i + 1]
        if l1[0] not in "PV" or len(l2) < 28:
            continue
        l2 = l2[:44].ljust(44, "<")
        number = _fix_checked(l2[0:9], l2[9], "XXXXXXXXX") or None
        dob = _fix_checked(l2[13:19], l2[19], "999999")
        expiry = _fix_checked(l2[21:27], l2[27], "999999")
        if not (number or dob or expiry):
            continue
        surname, given = _mrz_name(l1, 5)
        result = {
            "document": "Passport" if l1[0] == "P" else "Visa",
            "issuing_country": _shape(l1[2:5], "AAA").replace("<", ""),
            "surname": surname, "given_names": given,
            "nationality": _shape(l2[10:13], "AAA").replace("<", ""),
            "sex": {"M": "Male", "F": "Female"}.get(l2[20], ""),
            "number": number.replace("<", "") if number else None,
            "dob": _mrz_date(dob, False, today) if dob else None,
            "expiry": _mrz_date(expiry, True, today) if expiry else None,
        }
        return result
    return None
