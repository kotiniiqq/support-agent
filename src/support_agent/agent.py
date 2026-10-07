"""The pipeline: pre-gate -> retrieval -> answer, with a handoff on every other path.

`Agent.handle` never raises. Whatever goes wrong becomes a handoff with a summary
for the human agent, so a broken model or index cannot leave a customer unanswered
or send them something wrong. The pre-gate runs before the index is even built,
so a sensitive ticket still reaches a person when the index is down.
"""
import os
import time
from typing import Callable

from . import answer, tracing
from .kb import load_articles
from .llm import LLMResult, complete, llm_configured
from .models import ANSWER, HANDOFF, Customer, Decision, Hit, Ticket
from .pregate import check
from .retrieval import Retriever, make_retriever
from .summary import build_summary

# no-match thresholds per retriever, chosen from the sweeps in evals/RESULTS.md: the lowest value
# with zero wrong answers on the golden set. Scores from different retrievers are not comparable,
# and a real embedding model needs its own sweep before use.
DEFAULT_THRESHOLDS = {"bm25": 0.15, "qdrant": 0.25}


class Agent:
    def __init__(self, retriever: Retriever | Callable[[], Retriever] | None = None,
                 threshold: float | None = None, llm: Callable[..., LLMResult] | None = None):
        # a retriever, or a factory for one: building an index can fail (Qdrant down) and must
        # not stop the pre-gate from routing billing or personal-data tickets to a person
        self._retriever = retriever
        if threshold is None:
            env = os.environ.get("SA_THRESHOLD")
            threshold = float(env) if env else DEFAULT_THRESHOLDS.get(self.retriever_name, 0.15)
        self.threshold = threshold
        self.llm = llm if llm is not None else (complete if llm_configured() else None)
        self.articles = {a.id: a for a in load_articles()}

    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = make_retriever()
        elif callable(self._retriever) and not hasattr(self._retriever, "search"):
            self._retriever = self._retriever()
        return self._retriever

    @property
    def retriever_name(self) -> str:
        r = self._retriever
        return getattr(r, "name", None) or os.environ.get("SA_RETRIEVER", "bm25")

    def handle(self, ticket: Ticket) -> Decision:
        started = time.perf_counter()
        hits: list[Hit] = []
        try:
            ticket = _normalise(ticket)
            decision, hits = self._decide(ticket)
        except Exception as exc:  # noqa: BLE001 - the customer must never be left without a person
            decision = Decision(HANDOFF, "error", evidence=f"{type(exc).__name__}: {exc}")
        if decision.route == HANDOFF:
            try:
                decision.summary = build_summary(ticket, decision.reason, decision.evidence, hits)
            except Exception:  # noqa: BLE001 - a broken ticket must still produce a usable note
                decision.summary = f"Handoff: {decision.reason}. The ticket could not be summarised."
        tracing.trace("decision", ticket=getattr(ticket, "id", None), route=decision.route,
                      reason=decision.reason, score=decision.score, sources=decision.sources,
                      mode=decision.mode, retriever=self.retriever_name, threshold=self.threshold,
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
        grounded = [h for h in hits if h.score >= self.threshold]  # the model only sees what passed
        try:
            text, sources, result = answer.with_llm(ticket, grounded, self.llm)
        except answer.Escalate as esc:
            return Decision(HANDOFF, esc.reason, evidence=str(esc), score=top, mode="llm"), grounded
        tracing.trace("llm", ticket=ticket.id, model=result.model, prompt_tokens=result.prompt_tokens,
                      completion_tokens=result.completion_tokens, cost_usd=result.cost_usd,
                      latency_ms=result.latency_ms)
        return Decision(ANSWER, answer=text, sources=sources, score=top, mode="llm"), grounded


def _normalise(ticket: Ticket) -> Ticket:
    """Tolerate the shapes integrations actually send: missing text, numbers, no customer."""
    text = ticket.text if isinstance(ticket.text, str) else ("" if ticket.text is None else str(ticket.text))
    customer = ticket.customer if isinstance(ticket.customer, Customer) else Customer()
    return Ticket(id=str(ticket.id), text=text, customer=customer, channel=ticket.channel)
