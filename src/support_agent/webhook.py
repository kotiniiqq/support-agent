"""Chatwoot webhook: incoming customer message -> agent -> reply or handoff.

    support-agent serve            # uvicorn on :8000
    POST /webhook/chatwoot?token=$CHATWOOT_WEBHOOK_TOKEN

Without CHATWOOT_* variables the endpoint runs in dry-run mode and only returns
the action it would take, which is how the tests and local demos use it.
"""
import hmac
import os

from fastapi import FastAPI, HTTPException, Request

from .agent import Agent
from .chatwoot import ChatwootClient, ChatwootError, from_env
from .models import ANSWER, Customer, Ticket
from .tracing import trace


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


def create_app(agent: Agent | None = None, chatwoot: ChatwootClient | None = None,
               token: str | None = None) -> FastAPI:
    app = FastAPI(title="support-agent")
    state = {"agent": agent, "chatwoot": chatwoot if chatwoot is not None else from_env(),
             "token": token if token is not None else os.environ.get("CHATWOOT_WEBHOOK_TOKEN", "")}

    def get_agent() -> Agent:
        if state["agent"] is None:
            state["agent"] = Agent()
        return state["agent"]

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "chatwoot": state["chatwoot"] is not None}

    @app.post("/webhook/chatwoot")
    async def webhook(request: Request) -> dict:
        if state["token"] and not hmac.compare_digest(request.query_params.get("token", ""), state["token"]):
            raise HTTPException(status_code=401, detail="bad token")
        event = await request.json()
        # only new customer messages; our own replies and private notes would loop back otherwise
        if (event.get("event") != "message_created" or event.get("message_type") != "incoming"
                or event.get("private")):
            return {"action": "ignored"}
        ticket = ticket_from_event(event)
        decision = get_agent().handle(ticket)
        conversation_id = (event.get("conversation") or {}).get("id")
        action = "reply" if decision.route == ANSWER else "handoff"
        client = state["chatwoot"]
        if client is not None and conversation_id is not None:
            try:
                if action == "reply":
                    client.send_reply(conversation_id, decision.answer)
                else:
                    client.add_private_note(conversation_id, decision.summary)
                    client.open_for_agents(conversation_id)
            except ChatwootError as exc:
                trace("chatwoot_error", ticket=ticket.id, error=str(exc))
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"action": action, "dry_run": client is None, "reason": decision.reason,
                "sources": decision.sources,
                "content": decision.answer if action == "reply" else decision.summary}

    return app


app = create_app()
