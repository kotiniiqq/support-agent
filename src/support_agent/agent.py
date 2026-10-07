"""The pipeline: pre-gate -> retrieval -> answer, with a handoff on every other path.

`Agent.handle` never raises. Whatever goes wrong becomes a handoff with a summary
for the human agent, so a broken model or index cannot leave a customer unanswered
or send them something wrong.
"""
import os
import time
from typing import Callable

from . import answer, tracing
from .kb import load_articles
from .llm import LLMResult, complete, llm_configured
from .models import ANSWER, HANDOFF, Decision, Hit, Ticket
from .pregate import check
from .retrieval import Retriever, make_retriever
from .summary import build_summary

DEFAULT_THRESHOLD = 0.15  # chosen from the threshold sweep in evals/RESULTS.md


class Agent:
    def __init__(self, retriever: Retriever | None = None, threshold: float | None = None,
                 llm: Callable[..., LLMResult] | None = None):
        self.retriever = retriever or make_retriever()
        self.threshold = threshold if threshold is not None else float(os.environ.get("SA_THRESHOLD", DEFAULT_THRESHOLD))
        self.llm = llm if llm is not None else (complete if llm_configured() else None)
        self.articles = {a.id: a for a in load_articles()}

    def handle(self, ticket: Ticket) -> Decision:
        started = time.perf_counter()
        hits: list[Hit] = []
        try:
            decision, hits = self._decide(ticket)
        except Exception as exc:  # noqa: BLE001 - the customer must never be left without a person
            decision = Decision(HANDOFF, "error", evidence=f"{type(exc).__name__}: {exc}")
        if decision.route == HANDOFF:
            decision.summary = build_summary(ticket, decision.reason, decision.evidence, hits)
        tracing.trace("decision", ticket=ticket.id, route=decision.route, reason=decision.reason,
                      score=decision.score, sources=decision.sources, mode=decision.mode,
                      retriever=self.retriever.name, threshold=self.threshold,
                      latency_ms=int((time.perf_counter() - started) * 1000))
        return decision

    def _decide(self, ticket: Ticket) -> tuple[Decision, list[Hit]]:
        gate = check(ticket)
        if gate:
            return Decision(HANDOFF, gate.reason, evidence=gate.evidence), []
        hits = self.retriever.search(ticket.text, k=3)
        top = hits[0].score if hits else 0.0
        if top < self.threshold:
            return Decision(HANDOFF, "no_match", score=top), hits
        if self.llm is None:
            best = self.articles[hits[0].article_id]
            return Decision(ANSWER, answer=answer.extractive(best), sources=[best.id], score=top,
                            mode="extractive"), hits
        try:
            text, sources, result = answer.with_llm(ticket, hits, self.llm)
        except answer.Escalate as esc:
            return Decision(HANDOFF, esc.reason, evidence=str(esc), score=top, mode="llm"), hits
        tracing.trace("llm", ticket=ticket.id, model=result.model, prompt_tokens=result.prompt_tokens,
                      completion_tokens=result.completion_tokens, cost_usd=result.cost_usd,
                      latency_ms=result.latency_ms)
        return Decision(ANSWER, answer=text, sources=sources, score=top, mode="llm"), hits
