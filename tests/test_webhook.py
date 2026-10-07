import json

import httpx
import pytest
from fastapi.testclient import TestClient

from support_agent.agent import Agent
from support_agent.chatwoot import ChatwootClient, ChatwootError
from support_agent.retrieval import BM25Retriever
from support_agent.webhook import create_app


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("SA_TRACE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture(scope="module")
def agent():
    return Agent(BM25Retriever())


def event(content, vip=False, message_type="incoming", private=False):
    return {"event": "message_created", "id": 501, "message_type": message_type, "private": private,
            "content": content, "account": {"id": 1},
            "conversation": {"id": 42, "status": "pending", "labels": []},
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


def test_dry_run_returns_the_reply(agent):
    client = TestClient(create_app(agent, chatwoot=None, token=""))
    body = client.post("/webhook/chatwoot", json=event("How do I restart my server?")).json()
    assert body["action"] == "reply" and body["dry_run"] and body["sources"] == ["restart-server"]


def test_outgoing_and_private_messages_are_ignored(agent):
    client = TestClient(create_app(agent, chatwoot=None, token=""))
    assert client.post("/webhook/chatwoot", json=event("hi", message_type="outgoing")).json() == {"action": "ignored"}
    assert client.post("/webhook/chatwoot", json=event("hi", private=True)).json() == {"action": "ignored"}


def test_reply_is_posted_to_chatwoot(agent):
    rec = Recorder()
    client = TestClient(create_app(agent, chatwoot=chatwoot(rec), token=""))
    client.post("/webhook/chatwoot", json=event("How do I restart my server?"))
    path, body, token = rec.calls[0]
    assert path == "/api/v1/accounts/1/conversations/42/messages"
    assert body["private"] is False and "[restart-server]" in body["content"] and token == "secret"


def test_handoff_posts_a_private_note_and_opens_the_conversation(agent):
    rec = Recorder()
    client = TestClient(create_app(agent, chatwoot=chatwoot(rec), token=""))
    body = client.post("/webhook/chatwoot", json=event("How do I restart my server?", vip=True)).json()
    assert body["action"] == "handoff" and body["reason"] == "vip"
    (note_path, note, _), (status_path, status, _) = rec.calls
    assert note["private"] is True and "VIP" in note["content"]
    assert status_path.endswith("/conversations/42/toggle_status") and status == {"status": "open"}


def test_chatwoot_failure_is_a_502_not_a_silent_success(agent):
    client = TestClient(create_app(agent, chatwoot=chatwoot(Recorder(status=500)), token=""))
    assert client.post("/webhook/chatwoot", json=event("How do I restart my server?")).status_code == 502


def test_token_is_required_when_configured(agent):
    client = TestClient(create_app(agent, chatwoot=None, token="s3cret"))
    assert client.post("/webhook/chatwoot", json=event("hi")).status_code == 401
    assert client.post("/webhook/chatwoot?token=s3cret", json=event("hi")).status_code == 200


def test_health(agent):
    assert TestClient(create_app(agent, chatwoot=None, token="")).get("/health").json() == {"ok": True, "chatwoot": False}


def test_client_raises_on_http_errors():
    with pytest.raises(ChatwootError):
        chatwoot(Recorder(status=404)).send_reply(1, "x")


def test_vip_label_on_the_conversation_counts(agent):
    e = event("How do I restart my server?")
    e["conversation"]["labels"] = ["vip"]
    body = TestClient(create_app(agent, chatwoot=None, token="")).post("/webhook/chatwoot", json=e).json()
    assert body["reason"] == "vip"
