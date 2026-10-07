import json

import httpx
import pytest
from fastapi.testclient import TestClient

from support_agent.agent import Agent
from support_agent.chatwoot import ChatwootClient, ChatwootError
from support_agent.retrieval import BM25Retriever
from support_agent.webhook import create_app

TOKEN = {"X-Webhook-Token": "t0k3n"}


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("SA_TRACE_DIR", str(tmp_path))
    for k in ("OPENROUTER_API_KEY", "CHATWOOT_URL", "CHATWOOT_ACCOUNT_ID", "CHATWOOT_API_TOKEN", "CHATWOOT_WEBHOOK_TOKEN"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(scope="module")
def agent():
    return Agent(BM25Retriever())


_ids = iter(range(1000, 10_000))


def event(content, vip=False, message_type="incoming", private=False, status="pending", assignee=None):
    return {"event": "message_created", "id": next(_ids), "message_type": message_type, "private": private,
            "content": content, "account": {"id": 1},
            "conversation": {"id": 42, "status": status, "labels": [], "assignee_id": assignee},
            "sender": {"id": 7, "name": "Ann", "type": "contact",
                       "custom_attributes": {"plan": "pro", "vip": vip}}}


class Recorder:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def __call__(self, request):
        self.calls.append((request.url.path, json.loads(request.content), request.headers["api_access_token"]))
        return httpx.Response(self.status, json={"id": 1})


def chatwoot(recorder):
    return ChatwootClient("https://cw.example", 1, "secret", client=httpx.Client(transport=httpx.MockTransport(recorder)))


def dry(agent):
    return TestClient(create_app(agent, chatwoot=None, token=""))


def live(agent, rec):
    return TestClient(create_app(agent, chatwoot=chatwoot(rec), token="t0k3n"))


def test_dry_run_returns_the_reply(agent):
    body = dry(agent).post("/webhook/chatwoot", json=event("How do I restart my server?")).json()
    assert body["action"] == "reply" and body["dry_run"] and body["sources"] == ["restart-server"]


@pytest.mark.parametrize("kwargs, why", [
    ({"message_type": "outgoing"}, "not from the customer"),
    ({"private": True}, "private note"),
    ({"status": "open"}, "conversation is with the agents"),
    ({"assignee": 5}, "a person is assigned"),
])
def test_bot_stays_silent_outside_its_own_conversations(agent, kwargs, why):
    body = dry(agent).post("/webhook/chatwoot", json=event("How do I restart my server?", **kwargs)).json()
    assert body == {"action": "ignored", "why": why}


def test_reply_is_posted_to_chatwoot(agent):
    rec = Recorder()
    live(agent, rec).post("/webhook/chatwoot", json=event("How do I restart my server?"), headers=TOKEN)
    path, body, token = rec.calls[0]
    assert path == "/api/v1/accounts/1/conversations/42/messages"
    assert body["private"] is False and "[restart-server]" in body["content"] and token == "secret"


def test_handoff_posts_a_private_note_and_opens_the_conversation(agent):
    rec = Recorder()
    body = live(agent, rec).post("/webhook/chatwoot", json=event("How do I restart my server?", vip=True),
                                 headers=TOKEN).json()
    assert body["action"] == "handoff" and body["reason"] == "vip"
    (_, note, _), (status_path, status, _) = rec.calls
    assert note["private"] is True and "VIP" in note["content"]
    assert status_path.endswith("/conversations/42/toggle_status") and status == {"status": "open"}


def test_redelivered_event_is_not_answered_twice(agent):
    rec = Recorder()
    client, e = live(agent, rec), event("How do I restart my server?")
    client.post("/webhook/chatwoot", json=e, headers=TOKEN)
    second = client.post("/webhook/chatwoot", json=e, headers=TOKEN).json()
    assert second == {"action": "ignored", "why": "duplicate delivery"} and len(rec.calls) == 1


def test_chatwoot_failure_is_a_502_and_the_retry_is_allowed(agent):
    client, e = live(agent, Recorder(status=500)), event("How do I restart my server?")
    assert client.post("/webhook/chatwoot", json=e, headers=TOKEN).status_code == 502
    assert client.post("/webhook/chatwoot", json=e, headers=TOKEN).status_code == 502  # not swallowed as a duplicate


def test_token_is_checked_from_header_or_query(agent):
    client = live(agent, Recorder())
    assert client.post("/webhook/chatwoot", json=event("hi")).status_code == 401
    assert client.post("/webhook/chatwoot", json=event("hi"), headers={"X-Webhook-Token": "nope"}).status_code == 401
    assert client.post("/webhook/chatwoot?token=t0k3n", json=event("hi")).status_code == 200


def test_live_mode_refuses_to_start_without_a_token(agent):
    with pytest.raises(RuntimeError, match="CHATWOOT_WEBHOOK_TOKEN"):
        create_app(agent, chatwoot=chatwoot(Recorder()), token="")


def test_malformed_body_is_a_client_error(agent):
    client = dry(agent)
    assert client.post("/webhook/chatwoot", content=b"not json", headers={"content-type": "application/json"}).status_code == 422
    assert client.post("/webhook/chatwoot", json=[1, 2]).status_code == 422


def test_sensitive_ticket_reaches_a_person_even_when_the_index_is_down():
    def broken_index():
        raise ConnectionError("qdrant unreachable")
    body = dry(Agent(retriever=broken_index)).post("/webhook/chatwoot", json=event("refund please")).json()
    assert (body["action"], body["reason"]) == ("handoff", "billing")
    body = dry(Agent(retriever=broken_index)).post("/webhook/chatwoot", json=event("How do I restart my server?")).json()
    assert (body["action"], body["reason"]) == ("handoff", "error")


def test_vip_label_on_the_conversation_counts(agent):
    e = event("How do I restart my server?")
    e["conversation"]["labels"] = ["vip"]
    assert dry(agent).post("/webhook/chatwoot", json=e).json()["reason"] == "vip"


def test_health(agent):
    assert dry(agent).get("/health").json() == {"ok": True, "chatwoot": False}


def test_client_raises_on_http_errors_and_tolerates_empty_bodies():
    with pytest.raises(ChatwootError):
        chatwoot(Recorder(status=404)).send_reply(1, "x")
    empty = ChatwootClient("https://cw", 1, "s", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(204))))
    assert empty.open_for_agents(1) == {}


def test_bad_account_id_is_a_clear_error(monkeypatch):
    from support_agent.chatwoot import from_env
    monkeypatch.setenv("CHATWOOT_URL", "https://cw")
    monkeypatch.setenv("CHATWOOT_ACCOUNT_ID", "abc")
    monkeypatch.setenv("CHATWOOT_API_TOKEN", "x")
    with pytest.raises(RuntimeError, match="must be a number"):
        from_env()
