"""Command line: `support-agent <command>`. Run with --help for the list."""
import argparse
import json
import sys

from .agent import Agent
from .models import ANSWER, Customer, Ticket
from .retrieval import make_retriever

# CI gate on the default retriever: sensitive tickets must always reach a person,
# no customer may get a wrong answer, and routing must stay above this accuracy
MIN_ROUTING_ACCURACY = 0.85


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
    if args.command == "ask":
        return _ask(args)
    if args.command == "eval":
        return _eval(args)
    if args.command == "stats":
        from .tracing import read_traces, stats
        print(json.dumps(stats(read_traces()), indent=2))
        return 0
    import uvicorn
    uvicorn.run("support_agent.webhook:app", host=args.host, port=args.port)
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
    gate = report["results"][0]
    problems = []
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
