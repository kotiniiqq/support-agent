import pytest

from support_agent.agent import Agent
from support_agent.llm import LLMError, LLMResult
from support_agent.models import Customer, Ticket
from support_agent.retrieval import BM25Retriever
from support_agent.tracing import read_traces, stats


@pytest.fixture(autouse=True)
def traces(monkeypatch, tmp_path):
    monkeypatch.setenv("SA_TRACE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return tmp_path


@pytest.fixture(scope="module")
def retriever():
    return BM25Retriever()


def ticket(text, vip=False):
    return Ticket(id="T-1", text=text, customer=Customer(name="Ann", vip=vip))


def fake_llm(text):
    return lambda messages, model=None: LLMResult(text, "fake", 10, 5, 0.0, 1)


def test_answers_a_how_to_from_the_kb(retriever):
    d = Agent(retriever).handle(ticket("How do I restart my server?"))
    assert (d.route, d.sources, d.mode) == ("answer", ["restart-server"], "extractive")
    assert "Source: Restart your game server [restart-server]" in d.answer


def test_sensitive_ticket_never_reaches_retrieval(retriever):
    class Exploding:
        name = "boom"
        def search(self, q, k=3):
            raise AssertionError("retrieval must not run for sensitive tickets")
    d = Agent(Exploding()).handle(ticket("I want a refund"))
    assert (d.route, d.reason) == ("handoff", "billing")
    assert "billing or refund request" in d.summary


def test_off_topic_goes_to_a_person(retriever):
    d = Agent(retriever).handle(ticket("what do you think about the football final"))
    assert (d.route, d.reason) == ("handoff", "no_match")


def test_empty_ticket_is_a_handoff_not_a_crash(retriever):
    assert Agent(retriever).handle(ticket("   ")).reason == "no_match"


def test_broken_retriever_becomes_a_handoff():
    class Broken:
        name = "broken"
        def search(self, q, k=3):
            raise ConnectionError("qdrant is down")
    d = Agent(Broken()).handle(ticket("How do I restart my server?"))
    assert (d.route, d.reason) == ("handoff", "error")
    assert "qdrant is down" in d.summary or "qdrant is down" in d.evidence


def test_summary_redacts_personal_data(retriever):
    d = Agent(retriever).handle(ticket("Card 4111 1111 1111 1111, mail ann@example.com, help"))
    assert d.reason == "personal_data"
    assert "4111 1111" not in d.summary and "ann@example.com" not in d.summary


def test_llm_grounded_answer_is_used(retriever):
    llm = fake_llm("Press Restart in the panel.\n1. Open the panel\n2. Press Restart\n[restart-server]")
    d = Agent(retriever, llm=llm).handle(ticket("How do I restart my server?"))
    assert (d.route, d.mode, d.sources) == ("answer", "llm", ["restart-server"])


@pytest.mark.parametrize("text, reason", [
    ("ESCALATE", "llm_escalated"),
    ("Press Restart.", "ungrounded"),                        # no citation
    ("Press Restart. [billing-secrets]", "ungrounded"),      # cites an article it was not given
])
def test_llm_answers_that_are_not_grounded_go_to_a_person(retriever, text, reason):
    d = Agent(retriever, llm=fake_llm(text)).handle(ticket("How do I restart my server?"))
    assert (d.route, d.reason) == ("handoff", reason)


def test_llm_failure_goes_to_a_person(retriever):
    def broken(messages, model=None):
        raise LLMError("timeout")
    d = Agent(retriever, llm=broken).handle(ticket("How do I restart my server?"))
    assert (d.route, d.reason) == ("handoff", "error")


def test_every_decision_is_traced_and_redacted(retriever, traces):
    agent = Agent(retriever)
    agent.handle(ticket("How do I restart my server?"))
    agent.handle(ticket("refund to 4111 1111 1111 1111"))
    events = read_traces(traces)
    s = stats(events)
    assert s["tickets"] == 2 and s["answered"] == 1 and s["coverage"] == 0.5
    assert s["handoff_reasons"] == {"personal_data": 1}
    assert "4111" not in (traces / next(iter(p.name for p in traces.glob("*.jsonl")))).read_text()
