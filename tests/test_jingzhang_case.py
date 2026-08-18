"""End-to-end test: the Jingzhang 84/100 case replay runs and reports the
real recorded outcomes."""

import tempfile
from pathlib import Path

from switchback.cases.jingzhang import run_jingzhang_case


def test_jingzhang_case_replay():
    with tempfile.TemporaryDirectory() as tmp:
        summary = run_jingzhang_case(ws=Path(tmp), headless=True)

    assert summary["best_score"] == 84
    assert summary["chain_integrity"] is True

    verdicts = {r["version"]: r["verdict"] for r in summary["submissions"]}
    # 真实历史：v5 / v8.1 / v9.1 / v9.5 / v10 放行；v8 / v8.2 / v8.5 / v8.10 / v9.2 / v9.3 折返
    assert verdicts["v5"] == "RELEASED"
    assert verdicts["v8.1"] == "RELEASED"
    assert verdicts["v9.1"] == "RELEASED"
    assert verdicts["v9.5"] == "RELEASED"
    assert verdicts["v10"] == "RELEASED"
    assert verdicts["v8"] == "TURNED_BACK"
    assert verdicts["v8.2"] == "TURNED_BACK"
    assert verdicts["v8.10"] == "TURNED_BACK"
    assert verdicts["v9.2"] == "TURNED_BACK"
    assert verdicts["v9.3"] == "TURNED_BACK"

    assert summary["km_count"] >= len(summary["submissions"])  # 每版至少 K0 + 可能 K-release
    assert summary["risks"] >= 3
    assert summary["lessons"] >= 3
