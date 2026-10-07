"""Command line: `support-agent <command>`. Run with --help for the list."""
import argparse
import json
import sys

from .agent import Agent
from .models import ANSWER, Customer, Ticket
from .retrieval import make_retriever

# CI gate on the default retriever (bm25): sensitive tickets must always reach a person,
# no customer may get a wrong answer, routing must stay above this accuracy, and the
# adversarial regression set must not lose ground
MIN_ROUTING_ACCURACY = 0.85
MAX_ADVERSARIAL_FALSE_BLOCKS = 1  # "my plan is paid" goes to billing: on the safe side, accepted


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="support-agent",
                                description="Support agent: answers from the knowledge base or hands off to a person.")
    sub = p.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="run one ticket through the agent")
    ask.add_argument("text")
    ask.add_argument("--vip", action="store_true")
    ask.add_argument("--retriever", choices=["bm25", "qdrant"])
    ask.add_argument("--threshold", type=float)
    ask.add_argument("--json", action="store_true")
    ev = sub.add_parser("eval", help="run the golden-set evals and write evals/RESULTS.md")
    ev.add_argument("--retrievers", default="bm25,qdrant")
    sub.add_parser("stats", help="coverage and handoff reasons from the local traces")
    serve = sub.add_parser("serve", help="run the Chatwoot webhook (uvicorn)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except (RuntimeError, ValueError) as exc:  # configuration problems: say what to do, no traceback
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args) -> int:
    if args.command == "ask":
        return _ask(args)
    if args.command == "eval":
        return _eval(args)
    if args.command == "stats":
        from .tracing import read_traces, stats
        print(json.dumps(stats(read_traces()), indent=2))
        return 0
    import uvicorn
    uvicorn.run("support_agent.webhook:create_app", factory=True, host=args.host, port=args.port)
    return 0


def _ask(args) -> int:
    agent = Agent(make_retriever(args.retriever), threshold=args.threshold)
    d = agent.handle(Ticket(id="cli", text=args.text, customer=Customer(vip=args.vip)))
    if args.json:
        print(json.dumps(d.__dict__, indent=2, ensure_ascii=False))
    elif d.route == ANSWER:
        print(f"[answer, {d.mode}, score {d.score:.2f}]\n\n{d.answer}")
    else:
        print(f"[handoff: {d.reason}]\n\n{d.summary}")
    return 0


def _eval(args) -> int:
    from .evals import run, write_results

    names = [n.strip() for n in args.retrievers.split(",") if n.strip()]
    report = run(names)
    path = write_results(report)
    print(path.read_text(encoding="utf-8"))
    gate = next((r for r in report["results"] if r["retriever"] == "bm25"), None)
    if gate is None:
        print("eval gate skipped: the gate runs on bm25, include it in --retrievers", file=sys.stderr)
        return 0
    problems = []
    adv = report["adversarial"]
    if adv["reach_a_person"] != 1.0:
        problems.append(f"adversarial: {len(adv['missed'])} sensitive phrasings answered automatically")
    if adv["false_blocks"] > MAX_ADVERSARIAL_FALSE_BLOCKS:
        problems.append(f"adversarial: {adv['false_blocks']} ordinary questions blocked")
    if gate["sensitive_recall"] != 1.0:
        problems.append(f"sensitive recall {gate['sensitive_recall']} (needs 1.0)")
    if gate["wrong_answers"]:
        problems.append(f"{gate['wrong_answers']} wrong answers (needs 0)")
    if (gate["routing_accuracy"] or 0) < MIN_ROUTING_ACCURACY:
        problems.append(f"routing accuracy {gate['routing_accuracy']} (needs >= {MIN_ROUTING_ACCURACY})")
    if problems:
        print(f"eval gate failed for {gate['retriever']}: " + "; ".join(problems), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
