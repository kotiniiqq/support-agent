"""Chatwoot webhook: incoming customer message -> agent -> reply or handoff.

    support-agent serve
    POST /webhook/chatwoot   with header X-Webhook-Token (or ?token=) = CHATWOOT_WEBHOOK_TOKEN

The bot only speaks in conversations it owns: status "pending" and no human assignee.
Once it hands off (status "open") or an agent takes over, it stays silent.
Without CHATWOOT_* variables the endpoint runs in dry-run mode and only returns the
action it would take; with them, a webhook token is required.
"""
import hmac
import os
from collections import OrderedDict

from fastapi import Body, FastAPI, Header, HTTPException, Query

from .agent import Agent
from .chatwoot import ChatwootClient, ChatwootError, from_env
from .models import ANSWER, Customer, Ticket
from .tracing import trace

SEEN_LIMIT = 10_000  # remembered event ids, so a redelivered webhook is not answered twice


def _truthy(value) -> bool:
    return str(value).lower() in ("1", "true", "yes")


def ticket_from_event(event: dict) -> Ticket:
    sender = event.get("sender") or {}
    conversation = event.get("conversation") or {}
    attrs = sender.get("custom_attributes") or {}
    labels = conversation.get("labels") or []
    customer = Customer(name=sender.get("name") or "customer", plan=str(attrs.get("plan", "standard")),
                        vip=_truthy(attrs.get("vip")) or "vip" in labels)
    return Ticket(id=f"cw-{conversation.get('id')}-{event.get('id')}", text=event.get("content") or "",
                  customer=customer, channel="chatwoot")


def _ignored(event: dict) -> str | None:
    if event.get("event") != "message_created":
        return "not a new message"
    if event.get("message_type") not in ("incoming", 0):
        return "not from the customer"
    if event.get("private"):
        return "private note"
    conversation = event.get("conversation") or {}
    if conversation.get("status", "pending") != "pending":
        return "conversation is with the agents"
    if conversation.get("assignee_id") or (conversation.get("meta") or {}).get("assignee"):
        return "a person is assigned"
    return None


def create_app(agent: Agent | None = None, chatwoot: ChatwootClient | None = None,
               token: str | None = None) -> FastAPI:
    client = chatwoot if chatwoot is not None else from_env()
    secret = token if token is not None else os.environ.get("CHATWOOT_WEBHOOK_TOKEN", "")
    if client is not None and not secret:
        raise RuntimeError("CHATWOOT_WEBHOOK_TOKEN must be set when Chatwoot credentials are configured: "
                           "without it anyone could make the bot post into any conversation")
    app = FastAPI(title="support-agent")
    state = {"agent": agent, "seen": OrderedDict()}

    def get_agent() -> Agent:
        if state["agent"] is None:
            # the retriever is built lazily inside the agent, so a broken index cannot stop the pre-gate
            state["agent"] = Agent(retriever=None)
        return state["agent"]

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "chatwoot": client is not None}

    # a plain `def`: FastAPI runs it in a worker thread, so the synchronous agent and HTTP calls
    # do not block the event loop
    @app.post("/webhook/chatwoot")
    def webhook(event: dict = Body(...), x_webhook_token: str | None = Header(default=None),
                token_param: str | None = Query(default=None, alias="token")) -> dict:
        if secret and not hmac.compare_digest(x_webhook_token or token_param or "", secret):
            raise HTTPException(status_code=401, detail="bad token")
        if reason := _ignored(event):
            return {"action": "ignored", "why": reason}
        event_id = event.get("id")
        if event_id is not None:
            if event_id in state["seen"]:
                return {"action": "ignored", "why": "duplicate delivery"}
            state["seen"][event_id] = True
            if len(state["seen"]) > SEEN_LIMIT:
                state["seen"].popitem(last=False)

        ticket = ticket_from_event(event)
        decision = get_agent().handle(ticket)
        conversation_id = (event.get("conversation") or {}).get("id")
        action = "reply" if decision.route == ANSWER else "handoff"
        if client is not None and conversation_id is not None:
            try:
                if action == "reply":
                    client.send_reply(conversation_id, decision.answer)
                else:
                    client.add_private_note(conversation_id, decision.summary)
                    client.open_for_agents(conversation_id)
            except ChatwootError as exc:
                state["seen"].pop(event_id, None)  # let Chatwoot's retry try again
                trace("chatwoot_error", ticket=ticket.id, error=str(exc))
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"action": action, "dry_run": client is None, "reason": decision.reason,
                "sources": decision.sources,
                "content": decision.answer if action == "reply" else decision.summary}

    return app
