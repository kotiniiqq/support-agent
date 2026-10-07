"""Evals on the golden ticket set. No API key needed: this is the routing and
retrieval layer, which is what decides whether a customer gets an answer at all.

Metrics per retriever:
- routing accuracy (route and reason both right);
- sensitive recall: share of billing / personal-data / abuse / human / VIP tickets handed
  off with the right reason (the CI gate requires 1.0);
- false handoffs: answerable tickets sent to a person;
- coverage: share of all tickets answered automatically;
- answer accuracy: answered tickets that cite the expected article;
- retrieval hit@1 / hit@3 on answerable tickets;
- threshold sweep: coverage and answer accuracy as the no-match threshold moves.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import tracing
from .agent import Agent
from .models import ANSWER, SENSITIVE, Customer, Ticket
from .pregate import check
from .retrieval import Retriever, make_retriever

CASES = Path(__file__).resolve().parent / "eval_cases" / "tickets.yaml"
ADVERSARIAL = Path(__file__).resolve().parent / "eval_cases" / "adversarial.yaml"
SWEEP = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]


def load_cases(path: Path | None = None) -> list[dict]:
    return yaml.safe_load((path or CASES).read_text(encoding="utf-8"))


def _ticket(case: dict) -> Ticket:
    return Ticket(id=case["id"], text=case["text"], customer=Customer(vip=bool(case.get("vip"))))


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def evaluate(retriever: Retriever, cases: list[dict], threshold: float | None = None) -> dict:
    agent = Agent(retriever, threshold=threshold, llm=None)  # routing layer only: no LLM in evals
    rows = []
    for case in cases:
        d = agent.handle(_ticket(case))
        expected_route = case["route"]
        correct = (d.route == expected_route and
                   (d.sources[:1] == [case["article"]] if expected_route == ANSWER else d.reason == case["reason"]))
        rows.append({"id": case["id"], "expected": case.get("article") or case.get("reason"),
                     "got": (d.sources[:1] or [None])[0] if d.route == ANSWER else d.reason,
                     "route": d.route, "score": d.score, "correct": correct})
    by_id = {r["id"]: r for r in rows}
    answerable = [c for c in cases if c["route"] == ANSWER]
    sensitive = [c for c in cases if c.get("reason") in SENSITIVE]
    answered = [r for r in rows if r["route"] == ANSWER]

    hit1 = hit3 = 0
    for c in answerable:
        ids = [h.article_id for h in retriever.search(c["text"], k=3)]
        hit1 += ids[:1] == [c["article"]]
        hit3 += c["article"] in ids
    return {
        "retriever": retriever.name,
        "threshold": agent.threshold,
        "cases": len(cases),
        "routing_accuracy": _ratio(sum(r["correct"] for r in rows), len(rows)),
        "sensitive_recall": _ratio(sum(by_id[c["id"]]["correct"] for c in sensitive), len(sensitive)),
        "false_handoffs": sum(by_id[c["id"]]["route"] != ANSWER for c in answerable),
        "coverage": _ratio(len(answered), len(rows)),
        # of the tickets the KB can answer, how many were answered automatically and correctly
        "automated": _ratio(sum(by_id[c["id"]]["correct"] for c in answerable), len(answerable)),
        "answer_accuracy": _ratio(sum(r["correct"] for r in answered), len(answered)),
        "wrong_answers": sum(not r["correct"] for r in answered),
        "hit_at_1": _ratio(hit1, len(answerable)),
        "hit_at_3": _ratio(hit3, len(answerable)),
        "rows": rows,
    }


def sweep(retriever: Retriever, cases: list[dict], thresholds=SWEEP) -> list[dict]:
    out = []
    for t in thresholds:
        r = evaluate(retriever, cases, threshold=t)
        out.append({k: r[k] for k in ("threshold", "coverage", "automated", "answer_accuracy", "wrong_answers",
                                      "false_handoffs", "routing_accuracy")})
    return out


def evaluate_adversarial(cases: list[dict] | None = None) -> dict:
    """Pre-gate only: does every sensitive phrasing reach a person, and does no ordinary
    question get blocked? No retrieval involved, so the numbers do not depend on KB coverage."""
    cases = cases or load_cases(ADVERSARIAL)
    sensitive = [c for c in cases if c["kind"] == "sensitive"]
    ordinary = [c for c in cases if c["kind"] == "ordinary"]
    missed, wrong_reason, blocked = [], [], []
    for c in sensitive:
        gate = check(_ticket(c))
        if gate is None:
            missed.append(c["id"])
        elif gate.reason != c["reason"]:
            wrong_reason.append(f"{c['id']} ({gate.reason}, expected {c['reason']})")
    for c in ordinary:
        if (gate := check(_ticket(c))) is not None:
            blocked.append(f"{c['id']} ({gate.reason})")
    return {
        "sensitive": len(sensitive), "ordinary": len(ordinary),
        "reach_a_person": _ratio(len(sensitive) - len(missed), len(sensitive)),
        "exact_reason": _ratio(len(sensitive) - len(missed) - len(wrong_reason), len(sensitive)),
        "false_blocks": len(blocked),
        "missed": missed, "wrong_reason": wrong_reason, "blocked": blocked,
    }


def run(retrievers: list[str] | None = None, cases: list[dict] | None = None) -> dict:
    cases = cases or load_cases()
    results = []
    with tracing.suspended():
        for name in retrievers or ["bm25", "qdrant"]:
            try:
                retriever = make_retriever(name)
            except RuntimeError as exc:  # e.g. the optional qdrant extra is not installed
                print(f"skipping {name}: {exc}", file=sys.stderr)
                continue
            result = evaluate(retriever, cases)
            result["sweep"] = sweep(retriever, cases)
            results.append(result)
    return {"cases": len(cases), "results": results, "adversarial": evaluate_adversarial()}


def write_results(report: dict, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or Path.cwd() / "evals"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    (out_dir / "results").mkdir(parents=True, exist_ok=True)
    (out_dir / "results" / f"{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    lines = ["# Eval results", "",
             f"Last run: {stamp}. {report['cases']} golden tickets. Raw per-ticket data is written to "
             "`evals/results/` (not committed).", "",
             "| retriever | threshold | routing accuracy | sensitive recall | coverage | automated "
             "| answer accuracy | wrong answers | false handoffs | hit@1 | hit@3 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in report["results"]:
        lines.append(f"| {r['retriever']} | {r['threshold']} | {r['routing_accuracy']} | {r['sensitive_recall']} "
                     f"| {r['coverage']} | {r['automated']} | {r['answer_accuracy']} | {r['wrong_answers']} | {r['false_handoffs']} "
                     f"| {r['hit_at_1']} | {r['hit_at_3']} |")
    adv = report.get("adversarial")
    if adv:
        lines += ["", "## Adversarial set (pre-gate only)", "",
                  f"{adv['sensitive']} sensitive and {adv['ordinary']} ordinary phrasings written by an independent "
                  "reviewer to break the rules. The rules were fixed against it, so it is a regression set now, "
                  "not a held-out one.", "",
                  "| sensitive reaching a person | with the exact reason | ordinary questions blocked |",
                  "|---|---|---|",
                  f"| {adv['reach_a_person']} | {adv['exact_reason']} | {adv['false_blocks']} |"]
        if adv["missed"] or adv["blocked"] or adv["wrong_reason"]:
            lines += ["", "Missed: " + (", ".join(adv["missed"]) or "none") + ". Blocked: "
                      + (", ".join(adv["blocked"]) or "none") + ". Wrong reason: "
                      + (", ".join(adv["wrong_reason"]) or "none") + "."]
    for r in report["results"]:
        lines += ["", f"## Threshold sweep: {r['retriever']}", "",
                  "| threshold | coverage | automated | answer accuracy | wrong answers | false handoffs | routing accuracy |",
                  "|---|---|---|---|---|---|---|"]
        lines += [f"| {s['threshold']} | {s['coverage']} | {s['automated']} | {s['answer_accuracy']} | {s['wrong_answers']} "
                  f"| {s['false_handoffs']} | {s['routing_accuracy']} |" for s in r["sweep"]]
        misses = [f"`{x['id']}` (expected {x['expected']}, got {x['got']})" for x in r["rows"] if not x["correct"]]
        if misses:
            lines += ["", "Misrouted at the default threshold: " + ", ".join(misses)]
    path = out_dir / "RESULTS.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path
