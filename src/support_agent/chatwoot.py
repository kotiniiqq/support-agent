"""Minimal Chatwoot API client: reply, leave a private note, hand the conversation to agents.

    CHATWOOT_URL=https://app.chatwoot.com
    CHATWOOT_ACCOUNT_ID=1
    CHATWOOT_API_TOKEN=...      # an agent-bot or user access token

Tested against hand-written fixtures modelled on the Chatwoot API docs, not a live instance.
"""
import os

import httpx


class ChatwootError(Exception):
    pass


class ChatwootClient:
    def __init__(self, base_url: str, account_id: int, token: str, client: httpx.Client | None = None):
        self.base = f"{base_url.rstrip('/')}/api/v1/accounts/{account_id}/conversations"
        self.headers = {"api_access_token": token}
        self.http = client or httpx.Client(timeout=15)

    def _post(self, path: str, body: dict) -> dict:
        try:
            response = self.http.post(f"{self.base}/{path}", json=body, headers=self.headers)
        except httpx.HTTPError as exc:
            raise ChatwootError(f"cannot reach Chatwoot: {exc}") from exc
        if response.status_code >= 400:
            raise ChatwootError(f"Chatwoot returned {response.status_code} for {path}")
        return response.json()

    def send_reply(self, conversation_id: int, text: str) -> dict:
        return self._post(f"{conversation_id}/messages",
                          {"content": text, "message_type": "outgoing", "private": False})

    def add_private_note(self, conversation_id: int, text: str) -> dict:
        return self._post(f"{conversation_id}/messages",
                          {"content": text, "message_type": "outgoing", "private": True})

    def open_for_agents(self, conversation_id: int) -> dict:
        # conversations owned by an agent bot sit in "pending"; "open" puts them in the agents' queue
        return self._post(f"{conversation_id}/toggle_status", {"status": "open"})


def from_env() -> ChatwootClient | None:
    url, account, token = (os.environ.get(k) for k in ("CHATWOOT_URL", "CHATWOOT_ACCOUNT_ID", "CHATWOOT_API_TOKEN"))
    if not (url and account and token):
        return None
    return ChatwootClient(url, int(account), token)
