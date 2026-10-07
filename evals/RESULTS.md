# Eval results

Last run: 2026-10-07T16-00-10Z. 46 golden tickets. Raw per-ticket data is written to `evals/results/` (not committed).

| retriever | threshold | routing accuracy | sensitive recall | coverage | automated | answer accuracy | wrong answers | false handoffs | hit@1 | hit@3 |
|---|---|---|---|---|---|---|---|---|---|---|
| bm25 | 0.15 | 0.913 | 1.0 | 0.435 | 0.833 | 1.0 | 0 | 4 | 0.958 | 0.958 |
| qdrant | 0.15 | 0.891 | 1.0 | 0.5 | 0.875 | 0.913 | 2 | 3 | 0.917 | 0.958 |

## Threshold sweep: bm25

| threshold | coverage | automated | answer accuracy | wrong answers | false handoffs | routing accuracy |
|---|---|---|---|---|---|---|
| 0.05 | 0.587 | 0.958 | 0.852 | 4 | 1 | 0.891 |
| 0.1 | 0.5 | 0.917 | 0.957 | 1 | 2 | 0.935 |
| 0.15 | 0.435 | 0.833 | 1.0 | 0 | 4 | 0.913 |
| 0.2 | 0.391 | 0.75 | 1.0 | 0 | 6 | 0.87 |
| 0.25 | 0.326 | 0.625 | 1.0 | 0 | 9 | 0.804 |
| 0.3 | 0.217 | 0.417 | 1.0 | 0 | 14 | 0.696 |
| 0.4 | 0.174 | 0.333 | 1.0 | 0 | 16 | 0.652 |

Misrouted at the default threshold: `a12` (expected server-lag, got no_match), `a13` (expected server-lag, got no_match), `a20` (expected server-wont-start, got no_match), `a24` (expected restart-server, got no_match)

## Threshold sweep: qdrant

| threshold | coverage | automated | answer accuracy | wrong answers | false handoffs | routing accuracy |
|---|---|---|---|---|---|---|
| 0.05 | 0.63 | 0.917 | 0.759 | 7 | 0 | 0.848 |
| 0.1 | 0.565 | 0.917 | 0.846 | 4 | 0 | 0.913 |
| 0.15 | 0.5 | 0.875 | 0.913 | 2 | 3 | 0.891 |
| 0.2 | 0.391 | 0.667 | 0.889 | 2 | 8 | 0.783 |
| 0.25 | 0.304 | 0.542 | 0.929 | 1 | 11 | 0.739 |
| 0.3 | 0.304 | 0.542 | 0.929 | 1 | 11 | 0.739 |
| 0.4 | 0.152 | 0.292 | 1.0 | 0 | 17 | 0.63 |

Misrouted at the default threshold: `a12` (expected server-lag, got no_match), `a18` (expected custom-domain, got no_match), `a24` (expected restart-server, got no_match), `n06` (expected no_match, got restart-server), `n07` (expected no_match, got server-wont-start)
