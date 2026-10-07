"""Redact personal data before text reaches a trace, a summary or a model."""
import re

_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SECRET = re.compile(r"(?i)((?:password|пароль)(?:\s+is|\s*:|\s*-)\s*)\S+")


def _mask_card(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group())
    return f"[card ****{digits[-4:]}]"


def redact(text: str) -> str:
    text = _SECRET.sub(r"\1[secret]", text)
    text = _IBAN.sub("[iban]", text)
    text = _CARD.sub(_mask_card, text)
    return _EMAIL.sub("[email]", text)
