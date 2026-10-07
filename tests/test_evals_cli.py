import json

import pytest

from support_agent.cli import main
from support_agent.evals import evaluate, load_cases, sweep
from support_agent.retrieval import BM25Retriever


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("SA_TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(scope="module")
def result():
    return evaluate(BM25Retriever(), load_cases())


def test_golden_set_is_balanced():
    cases = load_cases()
    routes = [c["route"] for c in cases]
    assert len(cases) >= 40 and routes.count("answer") >= 20 and routes.count("handoff") >= 15
    assert len({c["id"] for c in cases}) == len(cases)


def test_sensitive_tickets_always_reach_a_person(result):
    assert result["sensitive_recall"] == 1.0


def test_default_threshold_gives_no_wrong_answers(result):
    assert result["wrong_answers"] == 0 and result["answer_accuracy"] == 1.0


def test_metrics_are_consistent(result):
    answered = sum(r["route"] == "answer" for r in result["rows"])
    assert result["coverage"] == round(answered / result["cases"], 3)
    assert 0 < result["hit_at_1"] <= result["hit_at_3"] <= 1


def test_lower_threshold_trades_safety_for_coverage():
    rows = sweep(BM25Retriever(), load_cases(), thresholds=[0.05, 0.15, 0.4])
    coverage = [r["coverage"] for r in rows]
    assert coverage == sorted(coverage, reverse=True)
    assert rows[0]["wrong_answers"] >= rows[1]["wrong_answers"] >= rows[2]["wrong_answers"]


def test_cli_ask_answers(capsys):
    assert main(["ask", "How do I restart my server?"]) == 0
    assert "[answer, extractive" in capsys.readouterr().out


def test_cli_ask_hands_off_vip(capsys):
    assert main(["ask", "How do I restart my server?", "--vip", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["reason"] == "vip"


def test_cli_eval_passes_the_gate_and_writes_results(tmp_path, capsys):
    assert main(["eval", "--retrievers", "bm25"]) == 0
    assert "Threshold sweep: bm25" in (tmp_path / "evals" / "RESULTS.md").read_text(encoding="utf-8")


def test_cli_stats_reads_traces(capsys):
    main(["ask", "How do I restart my server?"])
    main(["ask", "I want a refund"])
    capsys.readouterr()
    main(["stats"])
    s = json.loads(capsys.readouterr().out)
    assert s["tickets"] == 2 and s["handoff_reasons"] == {"billing": 1}


def test_evals_do_not_write_traces(tmp_path):
    from support_agent.evals import run
    run(["bm25"])
    assert not list((tmp_path / "traces").glob("*.jsonl"))


def test_adversarial_regression_set():
    from support_agent.evals import evaluate_adversarial
    r = evaluate_adversarial()
    assert r["reach_a_person"] == 1.0 and r["false_blocks"] <= 1
