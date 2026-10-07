"""One JSON line per decision in .traces/YYYY-MM-DD.jsonl (or SA_TRACE_DIR).

Text fields are redacted before writing. Tracing never raises: a failure is
reported on stderr and the decision goes out anyway.
"""
import json
import os
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .redact import redact


def trace_dir() -> Path:
    return Path(os.environ.get("SA_TRACE_DIR", ".traces"))


_suspended = False


@contextmanager
def suspended():
    """Evals replay many tickets; their decisions must not show up as real traffic in `stats`."""
    global _suspended
    previous, _suspended = _suspended, True
    try:
        yield
    finally:
        _suspended = previous


def trace(name: str, **fields) -> dict:
    event = {"id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(), "name": name,
             **{k: redact(v) if isinstance(v, str) else v for k, v in fields.items()}}
    if _suspended:
        return event
    try:
        folder = trace_dir()
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / f"{event['timestamp'][:10]}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001 - observability must not take the agent down
        print(f"[tracing] write failed: {exc}", file=sys.stderr)
    return event


def read_traces(folder: Path | None = None) -> list[dict]:
    folder = folder or trace_dir()
    events = []
    for path in sorted(folder.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def stats(events: list[dict]) -> dict:
    decisions = [e for e in events if e.get("name") == "decision"]
    answered = [e for e in decisions if e.get("route") == "answer"]
    reasons: dict[str, int] = {}
    for e in decisions:
        if e.get("route") == "handoff":
            reasons[e.get("reason") or "unknown"] = reasons.get(e.get("reason") or "unknown", 0) + 1
    return {
        "tickets": len(decisions),
        "answered": len(answered),
        "coverage": round(len(answered) / len(decisions), 3) if decisions else None,
        "handoff_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
    }
