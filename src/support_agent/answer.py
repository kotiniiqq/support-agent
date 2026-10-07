"""Compose an answer from retrieved articles: extractive by default, LLM when configured.

The LLM may only rephrase what the passages say and must cite them. A missing or
foreign citation, or an explicit ESCALATE, turns into a handoff instead of a reply.
"""
import re
from typing import Callable

from .kb import Article
from .llm import LLMResult
from .models import Hit, Ticket
from .redact import redact

# [article-id] or [article-id#2], any case; not markdown link text like [docs](http://...)
CITATION = re.compile(r"\[([A-Za-z0-9-]+)(?:#\d+)?\](?!\()")
ESCALATE = re.compile(r"\bESCALATE\b", re.I)
MIN_ANSWER_CHARS = 20  # a reply that is only a citation is not an answer

SYSTEM_PROMPT = """You are a support agent for a game-server hosting company.
Answer the customer using ONLY the passages below. Keep it short and practical: one sentence, then numbered steps.
After the answer write the source as [article-id] for every passage you used.
If the passages do not answer the question, reply with exactly: ESCALATE"""


class Escalate(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason


def extractive(article: Article) -> str:
    return (f"{article.sections.get('Summary', '').strip()}\n\n{article.sections.get('Steps', '').strip()}"
            f"\n\nSource: {article.title} [{article.id}]")


def with_llm(ticket: Ticket, hits: list[Hit], llm: Callable[..., LLMResult]) -> tuple[str, list[str], LLMResult]:
    passages = "\n\n".join(f"[{h.article_id}] {h.title}\n{h.text}" for h in hits)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"PASSAGES:\n{passages}\n\nCUSTOMER:\n{redact(ticket.text)}"}]
    result = llm(messages)
    text = result.text.strip()
    if ESCALATE.search(text):
        raise Escalate("llm_escalated", "the model could not answer from the passages")
    cited = list(dict.fromkeys(c.lower() for c in CITATION.findall(text)))
    allowed = {h.article_id for h in hits}
    if not cited:
        raise Escalate("ungrounded", "the answer cites no source")
    if unknown := [c for c in cited if c not in allowed]:
        raise Escalate("ungrounded", f"the answer cites articles that were not retrieved: {unknown}")
    if len(CITATION.sub("", text).strip()) < MIN_ANSWER_CHARS:
        raise Escalate("ungrounded", "the answer is only a citation")
    return text, cited, result
