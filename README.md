# support-agent

A customer-support agent that answers only from its knowledge base, sends sensitive tickets
to a person before any model sees them, and hands off with a ready-made note whenever it is
not sure. Every routing decision is measured on a golden set of tickets, in CI, without any
API key.

> Reference implementation of the support agent I hardened for a game-server hosting company:
> in production it went from handling about 30% of tickets to about 70%. That system ran on
> n8n, Qdrant and Chatwoot and its code is private; this repo rebuilds the parts that made it
> safe and measurable, in plain Python, on a **synthetic knowledge base and synthetic tickets**.
> The 30% → 70% figure belongs to the client system, not to this demo.

## Run it

```bash
git clone https://github.com/kotiniiqq/support-agent && cd support-agent
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

support-agent ask "server crashes right after start, console shows a java error"
```

```
[answer, extractive, score 0.41]

A server that stops right after starting usually has a broken mod, a wrong Java version or a corrupted config. The console log names the cause.

1. Open the Console tab and read the last error lines before the crash.
2. If a mod is named, remove it from /mods via SFTP and start again.
3. If the log mentions Java, choose the Java version that matches your game version in Settings.

Source: Server does not start or crashes [server-wont-start]
```

```bash
support-agent ask "Use my card 4111 1111 1111 1111 for the renewal"
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
ticket ─► pre-gate (rules) ──sensitive──► person: billing · personal data · abuse/legal · "real person" · VIP
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

- **Pre-gate** (`pregate.py`): deterministic rules in a fixed order. Card numbers are checked with
  Luhn, so a 16-digit order number is not mistaken for a card; IBANs and passwords typed into the
  chat count as personal data; keywords work in English, Ukrainian and Russian with word
  boundaries ("humanoid" is not "human"). Sensitive tickets never reach retrieval or a model.
- **Retrieval** (`retrieval.py`): BM25 in pure Python by default, or Qdrant (in-memory or a server)
  with a pluggable embedder. Scores are normalised to 0–1 against the best score the query could
  reach, so one threshold works for short and long questions.
- **Answer** (`answer.py`): without a key, the matching article's summary and steps, with the
  source. With `OPENROUTER_API_KEY` set, a model rephrases the retrieved passages and must cite
  them as `[article-id]`; no citation, an unknown citation or `ESCALATE` becomes a handoff.
- **Handoff note** (`summary.py`): reason, what triggered it, customer, the message with card
  numbers, IBANs, e-mails and passwords masked, and the closest articles, so the person starts
  with context instead of reading the whole thread.
- **The agent never raises** (`agent.py`): a failing index or model becomes a handoff with reason
  `error`. Nothing half-done goes to the customer.

## Evals: measured, not eyeballed

```bash
support-agent eval
```

46 golden tickets (`src/support_agent/eval_cases/tickets.yaml`): 24 answerable how-to questions,
15 sensitive ones and 7 outside the knowledge base. Latest run ([evals/RESULTS.md](evals/RESULTS.md)):

| retriever | routing accuracy | sensitive recall | answered of answerable | wrong answers | false handoffs | hit@1 |
|---|---|---|---|---|---|---|
| bm25 (default) | 0.913 | **1.0** | 0.833 | **0** | 4 | 0.958 |
| qdrant + hash embedder | 0.891 | 1.0 | 0.875 | 2 | 3 | 0.917 |

**The threshold is a product decision, and the sweep makes it visible.** For BM25, lowering the
no-match threshold from 0.15 to 0.10 answers more tickets but sends one wrong answer; at 0.05 there
are four. 0.15 is the default because a wrong answer to a customer costs more than an extra ticket
for a person:

| threshold | answered of answerable | wrong answers | false handoffs |
|---|---|---|---|
| 0.05 | 0.958 | 4 | 1 |
| 0.10 | 0.917 | 1 | 2 |
| **0.15** | **0.833** | **0** | 4 |
| 0.25 | 0.625 | 0 | 9 |

What the numbers also show, honestly:

- The **hash embedder is not a semantic model**: it answers "hello" with the crash article. It exists
  so the Qdrant path runs offline and in CI; plug in a real embedding model with `SA_EMBED_KEY`
  (any OpenAI-compatible `/embeddings` endpoint) for production use.
- A **Ukrainian question** about restarting is handed off: the knowledge base is English and BM25
  matches words, not meaning. A multilingual embedding model is the fix, not a bigger keyword list.
- The evals cover the **routing layer** (who answers and from which article), which runs without a key.
  Checking the wording of model-written answers needs an LLM judge and a key; the grounding check
  (citations must be retrieved articles) is unit-tested with a fake model.

CI fails if any sensitive ticket is answered automatically, if any answer cites the wrong article, or
if routing accuracy drops below 0.85.

## Chatwoot

```bash
export CHATWOOT_URL=https://app.chatwoot.com CHATWOOT_ACCOUNT_ID=1 CHATWOOT_API_TOKEN=...
export CHATWOOT_WEBHOOK_TOKEN=some-long-random-string
support-agent serve --host 0.0.0.0 --port 8000
# Chatwoot webhook URL: https://your-host/webhook/chatwoot?token=some-long-random-string
```

On a new incoming message the agent either posts the reply, or leaves a private note with the handoff
summary and moves the conversation from the bot's queue to the agents' queue. Outgoing messages and
private notes are ignored, so the bot never answers itself. VIP status comes from the contact's
`vip` custom attribute or a `vip` label. Without the `CHATWOOT_*` variables the endpoint runs in dry-run
mode and returns the action it would take. The client is **tested against fixtures modelled on the
Chatwoot API docs**, not against a live instance.

## Tracing

Every decision appends a line to `.traces/YYYY-MM-DD.jsonl` (route, reason, score, sources, retriever,
threshold, latency; personal data masked), and LLM calls add tokens and cost.
`support-agent stats` turns the traces into coverage and handoff reasons, which is the number a
support lead actually asks for.

## Project layout

```
src/support_agent/
  pregate.py  redact.py                   rules that decide before any model, and masking
  kb.py  retrieval.py                     knowledge base, BM25 and Qdrant
  answer.py  llm.py  summary.py           answer composition, grounding check, handoff note
  agent.py                                the pipeline; never raises
  webhook.py  chatwoot.py  cli.py         interfaces
  evals.py  tracing.py                    measurement
  kb/  eval_cases/                        synthetic articles and golden tickets (ship with the package)
scripts/write_kb.py                       regenerates the knowledge base
tests/                                    71 tests, no network
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
