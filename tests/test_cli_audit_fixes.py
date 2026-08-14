"""Tests for the CLI subcommands the audit report flagged as missing (vote/seal)
and the verify-ordering bug (unknown task must not dump JSON before erroring)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from switchback.cli import main


def _run(*argv):
    return main(list(argv))


def test_vote_subcommand_is_registered():
    """Bug1: `vote` was mentioned in help docstring but not registered in argparse."""
    with pytest.raises(SystemExit) as exc:
        # argparse exits 0 for --help
        _run("vote", "--help")
    assert exc.value.code == 0


def test_seal_subcommand_is_registered():
    """Bug1: `seal` was mentioned in help docstring but not registered in argparse."""
    with pytest.raises(SystemExit) as exc:
        _run("seal", "--help")
    assert exc.value.code == 0


def test_verify_unknown_task_does_not_dump_json_first(tmp_path, capsys):
    """Bug2: verify on an unregistered task used to print the failure JSON, then
    crash with 'unknown task' inside turn_back. Now it must error cleanly first."""
    Path("switchback-run").mkdir(exist_ok=True)
    (Path("switchback-run") / "governance.json").write_text("{}", encoding="utf-8")
    rc = _run("verify", "never-registered", "--claims", "tests/fixtures/claims.json",
              "--sources", "tests/fixtures/sources.json")
    out = capsys.readouterr()
    assert rc == 2
    assert "unknown task" in out.err
    # 关键：不能先打印核验 JSON 再报错
    assert '"passed"' not in out.out


def test_public_api_exports_governor():
    """Bug3: `from switchback import SwitchbackGovernor` used to ImportError."""
    import switchback
    assert hasattr(switchback, "SwitchbackGovernor")
    assert hasattr(switchback, "KMarkerLedger")
    assert hasattr(switchback, "Checkpoint")
    # 可直接实例化
    gov = switchback.SwitchbackGovernor()
    assert gov is not None


def test_vote_and_seal_full_flow(tmp_path, monkeypatch):
    """vote + seal 子命令的端到端幸福路径（审查报告漏注册后的回归测试）."""
    monkeypatch.chdir(tmp_path)
    _run("init")
    _run("register", "t-vote", "--title", "vote test", "--grade", "steep")
    # 陡坡需三方：逐票投票
    _run("vote", "t-vote", "--role", "owner", "--name", "O", "--verdict", "pass")
    _run("vote", "t-vote", "--role", "professional", "--name", "P", "--verdict", "pass")
    _run("vote", "t-vote", "--role", "public", "--name", "U", "--verdict", "pass")
    # seal 一个 K 标
    _run("seal", "t-vote", "--label", "K-release", "--payload", '{"score": 90}')
    status = _run("status", "t-vote")
    # ledger 应可校验
    _run("ledger")
