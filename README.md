# support-agent

A customer-support agent that answers only from its knowledge base, sends sensitive tickets
to a person before any model sees them, and hands off with a ready-made note whenever it is
not sure. Every routing decision is measured on a golden set of tickets plus an adversarial
set, in CI, without any API key.

> Reference implementation of the support agent I hardened for a game-server hosting company:
> in production it went from handling about 30% of tickets to about 70%. That system ran on
> n8n, Qdrant and Chatwoot and its code is private; this repo rebuilds the parts that made it
> safe and measurable, in plain Python, on a **synthetic knowledge base and synthetic tickets**.
> The 30% → 70% figure belongs to the client system, not to this demo.

## Run it

```bash
git clone https://github.com/kotiniiqq/support-agent && cd support-agent
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"                           # the Qdrant backend is the optional extra [qdrant]

support-agent ask "server crashes right after start, console shows a java error"
```

```
[answer, extractive, score 0.42]

A server that stops right after starting usually has a broken mod, a wrong Java version or a corrupted config. The console log names the cause.

1. Open the Console tab and read the last error lines before the crash.
2. If a mod is named, remove it from /mods via SFTP and start again.
3. If the log mentions Java, choose the Java version that matches your game version in Settings.

Source: Server does not start or crashes [server-wont-start]
```

```bash
support-agent ask "Use my card 4111.1111.1111.1111 for the renewal"
```

```
[handoff: personal_data]

Handoff: the message contains personal or payment data.
Customer: customer (standard).
Message: Use my card [card ****1111] for the renewal
Trigger: [card ****1111]
```

## How a ticket is routed

```
ticket ─► pre-gate (rules) ──sensitive──► person: personal data · billing · abuse/legal · asks for a person · VIP
              │ clear
              ▼
          retrieve top 3 ──best score < threshold──► person: no_match
              │
              ▼
          compose answer ──model says ESCALATE / cites nothing / cites an article it was not given──► person
              │                                    any exception anywhere ──► person: error
              ▼
          reply with the source article
```

- **Pre-gate** (`pregate.py`, `pii.py`). Deterministic rules in a fixed order, run before the
  index is even built.
  - **Personal data:** card numbers with any separator, confirmed by Luhn (so a 16-digit order
    number is not a card); IBANs in any case, confirmed by mod-97; phone numbers; passports;
    password-like tokens next to "password/пароль".
  - **Billing, legal and requests for a person:** word stems rather than exact words ("suing",
    "lawyers", Ukrainian and Russian case forms).
  - **Request context:** asking for a person needs one ("talk to an agent", "з'єднайте з
    оператором"), so "file manager" or "how do I make myself operator" stay how-to questions.
  - **Sensitive tickets** never reach retrieval or a model.
- **Retrieval** (`retrieval.py`). BM25 in pure Python by default, or Qdrant with a pluggable
  embedder. BM25 scores are normalised against the best score the query could reach. Pleasantries
  ("hi team, hope you're doing great…") are dropped, so a chatty ticket is not drowned by its own
  greeting.
- **Answer** (`answer.py`). Without a key, the matching article's summary and steps, with the
  source. With `OPENROUTER_API_KEY`, a model rephrases only the passages that passed the threshold
  and must cite them as `[article-id]`. No citation, an unknown citation, a reply that is only a
  citation, or `ESCALATE` anywhere becomes a handoff.
- **Handoff note** (`summary.py`). Reason, trigger, customer, the message with personal data
  masked, and the closest articles, so the person starts with context.
- **The agent never raises** (`agent.py`). A failing index, a broken model or a malformed ticket
  becomes a handoff. A billing ticket still reaches a person when the index is down.

## Evals: measured, not eyeballed

```bash
support-agent eval
```

**Golden set.** 50 tickets in `src/support_agent/eval_cases/tickets.yaml`:
- 28 answerable, including 4 long, chatty ones;
- 15 sensitive;
- 7 outside the knowledge base.

Latest run ([evals/RESULTS.md](evals/RESULTS.md)):

| retriever | threshold | routing accuracy | sensitive to a person | answered correctly, of answerable | wrong answers | false handoffs | hit@1 |
|---|---|---|---|---|---|---|---|
| bm25 (default) | 0.15 | 0.88 | 1.0 | 0.786 | **0** | 6 | 0.857 |
| qdrant + hash embedder | 0.25 | 0.70 | 1.0 | 0.464 | 0 | 15 | 0.893 |

**Adversarial set.** 62 sensitive and 23 ordinary phrasings, written by an independent reviewer
to break the pre-gate:
- "I am suing you", "соедините с оператором", "card 4111.1111.1111.1111", "how do I make myself
  operator", "my sftp password is not working"…
- The first version of the rules missed about 45 of them. That is how the stem-based rules above
  came about.
- Result now: **62/62 reach a person with the right reason**. One ordinary question is blocked:
  "how do I change the game version, my plan is paid" goes to billing, which errs on the safe side.
- The rules were fixed against this set, so it is now a regression set, not a held-out one.

**The threshold is a product decision, and the sweep makes it visible.** For BM25:

| threshold | answered correctly, of answerable | wrong answers | false handoffs |
|---|---|---|---|
| 0.05 | 0.857 | 6 | 2 |
| 0.10 | 0.857 | 2 | 3 |
| **0.15** | **0.786** | **0** | 6 |
| 0.25 | 0.714 | 0 | 8 |

The default is the lowest threshold with no wrong answer, because a wrong answer to a customer
costs more than an extra ticket for a person. Each retriever gets its own threshold: cosine
similarities and normalised BM25 scores are not on the same scale.

**What the numbers also show, honestly:**

- **Keyword retrieval stops at paraphrase.** "The whole world got wiped, can we roll it back?"
  never says *backup* or *restore*, so BM25 hands it off. The same goes for a Ukrainian question
  against an English knowledge base. That is a safe failure (a person gets it), and the fix is a
  real multilingual embedding model behind the Qdrant backend, not a longer keyword list.
- **The hash embedder is not a semantic model.** It exists so the Qdrant path runs offline and in
  CI. Plug a real one in with `SA_EMBED_KEY` (any OpenAI-compatible `/embeddings` endpoint), then
  run the sweep again to pick its threshold before using it.
- **The threshold was chosen on the same golden set it is reported on.** There is no held-out
  split yet. Treat 0.786 as an optimistic number.
- **The evals cover the routing layer** (who answers and from which article), which runs without
  a key. The wording of model-written answers needs an LLM judge and a key. The grounding check is
  unit-tested with a fake model.

CI fails if:
- any sensitive ticket, golden or adversarial, is answered automatically;
- any BM25 answer cites the wrong article;
- more than one ordinary adversarial question is blocked;
- routing accuracy drops below 0.85.

## Chatwoot

```bash
export CHATWOOT_URL=https://app.chatwoot.com CHATWOOT_ACCOUNT_ID=1 CHATWOOT_API_TOKEN=...
export CHATWOOT_WEBHOOK_TOKEN=some-long-random-string     # required whenever CHATWOOT_* is set
support-agent serve --host 0.0.0.0 --port 8000
# webhook: POST https://your-host/webhook/chatwoot with header X-Webhook-Token (or ?token=)
```

On a new customer message the agent either posts the reply, or leaves a private note with the
handoff summary and moves the conversation to the agents' queue (`pending` → `open`).

The bot only speaks in conversations it owns: status `pending` and no assignee. Once it hands off,
or a person takes over, it stays silent. Outgoing messages, private notes and redelivered events
are ignored.

The handler runs in a worker thread, so the synchronous agent does not block the server. Without
`CHATWOOT_*` it runs in dry-run mode and returns the action it would take. The client is **tested
against fixtures modelled on the Chatwoot API docs**, not against a live instance.

## Tracing

Every decision appends a line to `.traces/YYYY-MM-DD.jsonl`, with personal data masked:
- route, reason, score and sources;
- retriever, threshold and latency;
- for LLM calls, also tokens and cost.

`support-agent stats` turns the traces into coverage and handoff reasons, the number a support
lead asks for. Eval runs do not write traces, so they never inflate that number.

## Project layout

```
src/support_agent/
  pregate.py  pii.py  redact.py           rules that decide before any model; one set of PII detectors
  kb.py  retrieval.py                     knowledge base, BM25 and Qdrant
  answer.py  llm.py  summary.py           answer composition, grounding check, handoff note
  agent.py                                the pipeline; never raises
  webhook.py  chatwoot.py  cli.py         interfaces
  evals.py  tracing.py                    measurement
  kb/  eval_cases/                        synthetic articles, golden and adversarial tickets (ship with the package)
scripts/write_kb.py                       regenerates the knowledge base
tests/                                    130 tests, no network
```

## How this was built

1. A written design spec and implementation plan.
2. Test-first implementation, task by task, with every diff reviewed.
3. A review of the whole repository whose job was to break it.

That review is the most useful part of the history:
- **The safety claim was hollow.** The golden sensitive tickets reused the rules' own keywords,
  so "sensitive recall 1.0" proved nothing. The reviewer's paraphrases slipped through, and its
  phrasings are now the adversarial set.
- **The bot would have talked over human agents.** Once a conversation was handed off, it kept
  replying.
- **A billing ticket got a 500** instead of a handoff when Qdrant was down.
- **A greeting hid the question.** "Hi team, hope you're well…" pushed a simple question below
  the threshold.

All of these are fixed, and each fix is pinned by a test.

## License

MIT
