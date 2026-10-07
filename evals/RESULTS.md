# Eval results

Last run: 2026-10-07T16-17-10Z. 50 golden tickets. Raw per-ticket data is written to `evals/results/` (not committed).

| retriever | threshold | routing accuracy | sensitive recall | coverage | automated | answer accuracy | wrong answers | false handoffs | hit@1 | hit@3 |
|---|---|---|---|---|---|---|---|---|---|---|
| bm25 | 0.15 | 0.88 | 1.0 | 0.44 | 0.786 | 1.0 | 0 | 6 | 0.857 | 0.893 |
| qdrant | 0.25 | 0.7 | 1.0 | 0.26 | 0.464 | 1.0 | 0 | 15 | 0.893 | 0.929 |

## Adversarial set (pre-gate only)

62 sensitive and 23 ordinary phrasings written by an independent reviewer to break the rules. The rules were fixed against it, so it is a regression set now, not a held-out one.

| sensitive reaching a person | with the exact reason | ordinary questions blocked |
|---|---|---|
| 1.0 | 1.0 | 1 |

Missed: none. Blocked: x76 (billing). Wrong reason: none.

## Threshold sweep: bm25

| threshold | coverage | automated | answer accuracy | wrong answers | false handoffs | routing accuracy |
|---|---|---|---|---|---|---|
| 0.05 | 0.6 | 0.857 | 0.8 | 6 | 2 | 0.84 |
| 0.1 | 0.52 | 0.857 | 0.923 | 2 | 3 | 0.9 |
| 0.15 | 0.44 | 0.786 | 1.0 | 0 | 6 | 0.88 |
| 0.2 | 0.44 | 0.786 | 1.0 | 0 | 6 | 0.88 |
| 0.25 | 0.4 | 0.714 | 1.0 | 0 | 8 | 0.84 |
| 0.3 | 0.32 | 0.571 | 1.0 | 0 | 12 | 0.76 |
| 0.4 | 0.2 | 0.357 | 1.0 | 0 | 18 | 0.64 |

Misrouted at the default threshold: `a12` (expected server-lag, got no_match), `a20` (expected server-wont-start, got no_match), `a24` (expected restart-server, got no_match), `l02` (expected server-wont-start, got no_match), `l03` (expected backups, got no_match), `l04` (expected sftp-access, got no_match)

## Threshold sweep: qdrant

| threshold | coverage | automated | answer accuracy | wrong answers | false handoffs | routing accuracy |
|---|---|---|---|---|---|---|
| 0.05 | 0.64 | 0.893 | 0.781 | 7 | 1 | 0.84 |
| 0.1 | 0.56 | 0.893 | 0.893 | 3 | 1 | 0.92 |
| 0.15 | 0.46 | 0.786 | 0.957 | 1 | 6 | 0.86 |
| 0.2 | 0.4 | 0.679 | 0.95 | 1 | 9 | 0.8 |
| 0.25 | 0.26 | 0.464 | 1.0 | 0 | 15 | 0.7 |
| 0.3 | 0.26 | 0.464 | 1.0 | 0 | 15 | 0.7 |
| 0.4 | 0.16 | 0.286 | 1.0 | 0 | 20 | 0.6 |

Misrouted at the default threshold: `a02` (expected restart-server, got no_match), `a03` (expected change-game-version, got no_match), `a06` (expected install-mods, got no_match), `a08` (expected backups, got no_match), `a09` (expected sftp-access, got no_match), `a12` (expected server-lag, got no_match), `a13` (expected server-lag, got no_match), `a17` (expected custom-domain, got no_match), `a18` (expected custom-domain, got no_match), `a20` (expected server-wont-start, got no_match), `a23` (expected upload-world, got no_match), `a24` (expected restart-server, got no_match), `l02` (expected server-wont-start, got no_match), `l03` (expected backups, got no_match), `l04` (expected sftp-access, got no_match)
