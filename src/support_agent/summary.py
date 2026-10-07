"""The note a human agent sees on handoff: why, what triggered it, and where to start."""
from .models import Hit, Ticket
from .redact import redact

REASON_TEXT = {
    "personal_data": "the message contains personal or payment data",
    "billing": "billing or refund request",
    "abuse": "legal threat, fraud claim or abuse",
    "human_requested": "the customer asked for a person",
    "vip": "VIP customer",
    "no_match": "no knowledge-base article answers this",
    "llm_escalated": "the model could not answer from the articles",
    "ungrounded": "the drafted answer was not grounded in the articles",
    "error": "the agent failed; nothing was sent to the customer",
}


def build_summary(ticket: Ticket, reason: str, evidence: str | None, hits: list[Hit]) -> str:
    text = redact(ticket.text.strip())
    lines = [
        f"Handoff: {REASON_TEXT.get(reason, reason)}.",
        f"Customer: {ticket.customer.name} ({ticket.customer.plan}{', VIP' if ticket.customer.vip else ''}).",
        f"Message: {text[:200]}{'…' if len(text) > 200 else ''}",
    ]
    if evidence:
        lines.append(f"Trigger: {evidence}")
    if hits:
        lines.append("Closest articles: " + ", ".join(f"{h.title} [{h.article_id}] {h.score:.2f}" for h in hits[:3]))
    return "\n".join(lines)
