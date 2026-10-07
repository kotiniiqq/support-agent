"""Deterministic pre-gate: decide before any retrieval or LLM call whether a ticket
must go to a person. Rules run in a fixed order and the first match wins.

Order matters: personal data first (it must never reach a model or a log
unredacted), then money, then threats and legal, then explicit requests for a
human, then VIP customers.
"""
import re
from dataclasses import dataclass

from .models import Ticket
from .redact import redact


@dataclass
class GateResult:
    reason: str
    evidence: str  # redacted fragment that triggered the rule


def _words(*phrases: str) -> re.Pattern:
    # word boundaries that also work for Cyrillic; phrases may contain spaces
    body = "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in phrases)
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)", re.I)


CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b")
PASSWORD = re.compile(r"(?<!\w)(?:password|пароль)(?:\s+is|\s*:|\s*-)\s*\S+", re.I)

BILLING = _words(
    "refund", "refunds", "chargeback", "invoice", "invoices", "charged", "charge me", "billing",
    "payment", "payments", "paid twice", "credit card", "debit card", "my card", "money back",
    "повернення коштів", "рахунок", "оплата", "оплату", "оплатив", "гроші",
    "возврат", "верните деньги", "деньги", "счет", "счёт", "оплатил",
)
ABUSE = _words(
    "lawyer", "attorney", "sue", "court", "police", "legal action", "scam", "fraud", "threat",
    "юрист", "адвокат", "суд", "суду", "поліція", "поліцію", "полиция", "полицию",
    "шахраї", "шахрайство", "мошенники", "мошенничество",
)
HUMAN = _words(
    "real person", "human", "operator", "manager", "speak to someone", "talk to someone",
    "живий оператор", "живого оператора", "оператора", "оператор", "менеджер",
    "живой человек", "живого человека",
)


def luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _card(text: str) -> str | None:
    for match in CARD.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            return match.group()
    return None


def check(ticket: Ticket) -> GateResult | None:
    text = ticket.text
    personal = _card(text) or (m.group() if (m := IBAN.search(text)) else None) \
        or (m.group() if (m := PASSWORD.search(text)) else None)
    if personal:
        return GateResult("personal_data", redact(personal))
    for reason, pattern in (("billing", BILLING), ("abuse", ABUSE), ("human_requested", HUMAN)):
        if m := pattern.search(text):
            return GateResult(reason, m.group())
    if ticket.customer.vip:
        return GateResult("vip", f"VIP customer {ticket.customer.name}")
    return None
