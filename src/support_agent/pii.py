"""Personal-data detectors shared by the pre-gate (to route) and redaction (to mask).

One module so the two can never drift: whatever the gate recognises, redaction masks.
"""
import re
from dataclasses import dataclass

# card numbers: 13-19 digits with any common separator, confirmed by Luhn
CARD = re.compile(r"(?<!\d)(?:\d[ .\-/_]{0,2}){12,18}\d(?!\d)")
# IBAN: country code, check digits, 11-30 alphanumerics, spaces or dashes allowed; confirmed by mod-97
IBAN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}(?:[ -]?[A-Za-z0-9]){11,30}(?![A-Za-z0-9])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# phones: an explicit international prefix, or a phone word right before the digits
PHONE = re.compile(r"(?<![\w+])\+\d[\d ()\-]{8,18}\d(?!\d)"
                   r"|(?i:(?:phone|tel|call me at|номер|телефон)[^\d+]{0,12})(\+?\d[\d ()\-]{8,18}\d)(?!\d)")
PASSPORT = re.compile(r"(?i)(?:passport|паспорт)\D{0,12}([A-ZА-Я]{2}\s?\d{6,8})")
SECRET_WORD = re.compile(r"(?i)(?<!\w)(?:password|passwd|pass|pwd|pw|пароль|пароля)(?!\w)")


@dataclass
class Found:
    kind: str
    start: int
    end: int
    text: str


def luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def iban_ok(raw: str) -> bool:
    s = re.sub(r"[ -]", "", raw).upper()
    if not 15 <= len(s) <= 34:
        return False
    rearranged = s[4:] + s[:4]
    try:
        return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1
    except ValueError:
        return False


def _secret_tokens(text: str) -> list[Found]:
    """A token that looks like a password within four words after 'password': at least five
    characters and a digit or a symbol. 'my password is not working' has none; 'password
    hunter22' and 'Пароль от панели qwerty123' do."""
    out = []
    for word in SECRET_WORD.finditer(text):
        rest = text[word.end():]
        for i, token in enumerate(re.finditer(r"\S+", rest)):
            if i >= 4:
                break
            value = token.group().strip(".,;:!?\"'()[]")
            if (len(value) >= 5 and not value.startswith("http")
                    and (re.search(r"\d", value) or re.search(r"[^\w]", value))
                    and not re.fullmatch(r"[\d.:]+", value)):
                start = word.end() + token.start() + token.group().find(value)
                out.append(Found("secret", start, start + len(value), value))
                break
    return out


def find(text: str) -> list[Found]:
    """All personal data in `text`, IBANs before cards so one is never half-read as the other."""
    found: list[Found] = []

    def free(a: int, b: int) -> bool:
        return all(b <= f.start or a >= f.end for f in found)

    for m in IBAN.finditer(text):
        # the pattern can run on into the next word ("... 6600 1 for"); shorten until the checksum holds
        raw = m.group()
        for end in range(len(raw), 14, -1):
            at_group_boundary = end == len(raw) or raw[end] in " -"
            candidate = raw[:end]
            if at_group_boundary and iban_ok(candidate):
                found.append(Found("iban", m.start(), m.start() + len(candidate), candidate))
                break
    for m in CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and luhn_ok(digits) and free(m.start(), m.end()):
            found.append(Found("card", m.start(), m.end(), m.group()))
    for m in PHONE.finditer(text):
        a, b = (m.start(1), m.end(1)) if m.group(1) else (m.start(), m.end())
        if 10 <= len(re.sub(r"\D", "", text[a:b])) <= 15 and free(a, b):
            found.append(Found("phone", a, b, text[a:b]))
    for m in PASSPORT.finditer(text):
        if free(m.start(1), m.end(1)):
            found.append(Found("passport", m.start(1), m.end(1), m.group(1)))
    for f in _secret_tokens(text):
        if free(f.start, f.end):
            found.append(f)
    for m in EMAIL.finditer(text):
        if free(m.start(), m.end()):
            found.append(Found("email", m.start(), m.end(), m.group()))
    return sorted(found, key=lambda f: f.start)


def mask(f: Found) -> str:
    if f.kind == "card":
        last4 = re.sub(r"\D", "", f.text)[-4:]  # computed outside the f-string: Python 3.11 compatible
        return f"[card ****{last4}]"
    return f"[{f.kind}]"
