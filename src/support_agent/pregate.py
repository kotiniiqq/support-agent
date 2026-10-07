"""Deterministic pre-gate: decide before any retrieval or model call whether a ticket
must go to a person. Rules run in a fixed order and the first match wins.

Order matters: personal data first (it must never reach a model or a log
unredacted), then money, then threats and legal, then explicit requests for a
person, then VIP customers.

Patterns use word stems, not exact words ("suing", "lawyers", Cyrillic cases),
and requests for a person need request context, so "file manager" or "how do I
make myself operator" stay ordinary how-to questions.
"""
import re
from dataclasses import dataclass

from . import pii
from .models import Ticket
from .redact import redact

W = r"(?<![\w'])"   # word start that also works for Cyrillic
E = r"(?![\w'])"    # word end


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts), re.I)


BILLING = _rx(
    rf"{W}refund\w*", rf"{W}charge ?backs?{E}", rf"{W}invoice[sd]?{E}", rf"{W}receipts?{E}",
    rf"{W}(?:over)?charg(?:ed|es|ing){E}", rf"{W}charge me{E}", rf"{W}billed{E}", rf"{W}billing{E}",
    rf"{W}paid{E}", rf"{W}pay(?:ing)? twice{E}", rf"{W}payments?{E}(?! plugin)", rf"{W}paypal{E}",
    rf"{W}subscriptions?{E}", rf"{W}cancel(?:led|ed)?{E}", rf"{W}money{E}", rf"{W}(?:credit|debit) card{E}",
    rf"{W}my card{E}", rf"{W}renewal{E}",
    # uk / ru stems
    rf"{W}поверн\w* (?:кошт|грош)\w*", rf"{W}кошт\w*", rf"{W}грош\w*", rf"{W}списа\w*",
    rf"{W}рахун\w*", rf"{W}оплат\w*", rf"{W}плат[іеё]ж\w*", rf"{W}возврат\w*", rf"{W}верн\w+ (?:деньг|оплат)\w*",
    rf"{W}деньг\w*", rf"{W}денег{E}", rf"{W}сч[её]т(?:а|у|ом|е)?{E}", rf"{W}чек(?:а|у|и)?{E}",  # not "чекати" (to wait)
)
ABUSE = _rx(
    rf"{W}su(?:e|es|ed|ing){E}", rf"{W}lawsuits?{E}", rf"{W}lawyers?{E}", rf"{W}attorneys?{E}",
    rf"{W}solicitors?{E}", rf"{W}legal action{E}", rf"{W}police{E}", rf"{W}ftc{E}",
    rf"{W}consumer protection{E}", rf"{W}(?:file|filing) a complaint{E}", rf"{W}report (?:you|this){E}",
    rf"{W}this is (?:a )?(?:scam|fraud|theft){E}", rf"{W}you(?:'re| are)? (?:scammers|frauds|thieves){E}",
    rf"{W}you (?:hacked|stole|scammed){E}", rf"{W}fraud{E}", rf"{W}theft{E}",
    # uk / ru stems
    # "позов" is the noun "lawsuit" only; "позовіть" means "call someone" and belongs to HUMAN
    rf"{W}суд(?:у|і|е|ом)?{E}", rf"{W}позов(?:у|ом|и|ів)?{E}",
    rf"{W}поліці\w*", rf"{W}полици\w*", rf"{W}юрист\w*",
    rf"{W}адвокат\w*", rf"{W}шахра\w*", rf"{W}мошенни\w*", rf"{W}обман\w*",
)
PERSON = r"(?:human|person|people|agent|operator|manager|someone|somebody|staff|support team|support staff)"
HUMAN = _rx(
    rf"{W}(?:talk|speak|chat)(?: \w+){{0,3}} (?:to|with)(?: \w+){{0,3}} {PERSON}{E}",
    rf"{W}(?:connect|transfer|put) me(?: \w+){{0,3}} (?:to|through to|with)(?: \w+){{0,3}} {PERSON}{E}",
    rf"{W}(?:real|live) (?:human|person|agent|people){E}", rf"{W}live chat{E}",
    rf"{W}is there (?:a|any) (?:human|person|real person){E}",
    r"^\s*(?:a )?(?:human|operator|agent|person|real person)\s*(?:please|pls|plz)?[\s?!.]*$",
    # uk / ru: a request verb near operator / manager / person
    rf"{W}(?:поговорити|поговорить|з'?єднайте|соедините|позовіть|позовите|покличте|дайте|переключіть|переключите|"
    rf"зв'?яжіть|свяжите)(?: \S+){{0,3}} (?:оператор\w*|менеджер\w*|людин\w*|человек\w*|жив\w+)",
    r"^\s*(?:оператор|менеджер)\w*\s*[?!.]*\s*$",
)


@dataclass
class GateResult:
    reason: str
    evidence: str  # redacted fragment that triggered the rule


def luhn_ok(digits: str) -> bool:
    return pii.luhn_ok(digits)


def check(ticket: Ticket) -> GateResult | None:
    text = ticket.text if isinstance(ticket.text, str) else str(ticket.text or "")
    if found := pii.find(text):
        return GateResult("personal_data", ", ".join(pii.mask(f) for f in found))
    for reason, pattern in (("billing", BILLING), ("abuse", ABUSE), ("human_requested", HUMAN)):
        if m := pattern.search(text):
            return GateResult(reason, redact(m.group()))
    customer = ticket.customer
    if customer is not None and customer.vip:
        return GateResult("vip", f"VIP customer {customer.name}")
    return None
