"""Boundary tests: state-machine edges + K-marker chain conflicts + persistence.

These cover the gaps the reviewer rightly flagged — the happy-path tests in
test_protocol.py don't exercise the harder corners.
"""

import json
import tempfile
from pathlib import Path

import pytest

from switchback.governor import SwitchbackGovernor
from switchback.ledger import KMarkerLedger, LedgerIntegrityError
from switchback.protocol import (
    Checkpoint,
    CheckpointKind,
    Grade,
    NoAutoResumeError,
    PartyRole,
    PartyVote,
    SwitchState,
    SwitchbackError,
    TaskCard,
    Verdict,
)


# --------------------------------------------------------------------------- #
# 状态机边界：SIDING / 多轮折返 / 全 DEPOT 票
# --------------------------------------------------------------------------- #

def test_siding_rework_then_mainline_via_fresh_checkpoint():
    """侧线返工后，经全新折返点复核可回正线。"""
    gov = SwitchbackGovernor()
    gov.admit("s1", "task", Grade.MEDIUM)
    gov.switch("s1", SwitchState.MAINLINE, actor="a", reason="first release")
    gov.turn_back("s1", actor="veto", reason="rework")  # 进侧线
    assert gov.status("s1")["task"]["state"] == SwitchState.SIDING

    # 侧线不是 DEPOT，回正线不需要 re_enter_mainline；但仍应过折返点
    cp = gov.open_checkpoint("s1", CheckpointKind.APPROVAL)
    gov.vote(cp, PartyRole.OWNER, "o", Verdict.PASS)
    gov.vote(cp, PartyRole.PROFESSIONAL, "p", Verdict.PASS)
    assert cp.resolve() == Verdict.PASS
    assert gov.switch("s1", SwitchState.MAINLINE, actor="a", reason="rework passed") == SwitchState.MAINLINE


def test_repeated_turn_backs_accumulate_state_correctly():
    """连续多轮折返，状态始终停在 SIDING，不会意外漂移。"""
    gov = SwitchbackGovernor()
    gov.admit("s2", "task", Grade.GENTLE)
    gov.switch("s2", SwitchState.MAINLINE, actor="a", reason="release")
    for i in range(3):
        gov.turn_back("s2", actor="v", reason=f"rework round {i}")
        assert gov.status("s2")["task"]["state"] == SwitchState.SIDING
        gov.switch("s2", SwitchState.MAINLINE, actor="a", reason=f"re-fix {i}")
    # 第三轮仍在正线
    assert gov.status("s2")["task"]["state"] == SwitchState.MAINLINE


def test_all_depot_votes_force_depot_over_turn_back():
    """三方全投 DEPOT => 入段（比折返更安全的一票优先）。"""
    gov = SwitchbackGovernor()
    gov.admit("s3", "task", Grade.STEEP)
    cp = gov.open_checkpoint("s3", CheckpointKind.APPROVAL)
    gov.vote(cp, PartyRole.OWNER, "o", Verdict.DEPOT)
    gov.vote(cp, PartyRole.PROFESSIONAL, "p", Verdict.DEPOT)
    gov.vote(cp, PartyRole.PUBLIC, "u", Verdict.DEPOT)
    assert cp.resolve() == Verdict.DEPOT


def test_mixed_depot_and_turn_back_depot_wins():
    """DEPOT + TURN_BACK 混合票 => DEPOT（更安全的一票优先）。"""
    gov = SwitchbackGovernor()
    gov.admit("s4", "task", Grade.STEEP)
    cp = gov.open_checkpoint("s4", CheckpointKind.APPROVAL)
    gov.vote(cp, PartyRole.OWNER, "o", Verdict.TURN_BACK)
    gov.vote(cp, PartyRole.PROFESSIONAL, "p", Verdict.DEPOT)  # 入段
    gov.vote(cp, PartyRole.PUBLIC, "u", Verdict.PASS)
    assert cp.resolve() == Verdict.DEPOT


def test_checkpoint_cannot_be_revoted_after_decision():
    """已裁决的折返点拒绝再投票。"""
    gov = SwitchbackGovernor()
    gov.admit("s5", "task", Grade.GENTLE)
    cp = gov.open_checkpoint("s5", CheckpointKind.APPROVAL)
    gov.vote(cp, PartyRole.OWNER, "o", Verdict.PASS)
    cp.resolve()
    with pytest.raises(SwitchbackError):
        cp.add_vote(PartyVote(role=PartyRole.PROFESSIONAL, name="p", verdict=Verdict.PASS))


def test_mainline_to_depot_to_mainline_forbidden_then_allowed():
    """正线→入段→禁止自动回正线；→全新复核后允许回正线。"""
    gov = SwitchbackGovernor()
    gov.admit("s6", "task", Grade.MEDIUM)
    gov.switch("s6", SwitchState.MAINLINE, actor="a", reason="release")
    gov.pull_into_depot("s6", actor="safety", reason="incident")
    # 禁止自动恢复
    with pytest.raises(NoAutoResumeError):
        gov.switch("s6", SwitchState.MAINLINE, actor="x")
    # 全新 approval 通过后才能回
    cp = gov.open_checkpoint("s6", CheckpointKind.APPROVAL)
    gov.vote(cp, PartyRole.OWNER, "o", Verdict.PASS)
    gov.vote(cp, PartyRole.PROFESSIONAL, "p", Verdict.PASS)
    assert gov.re_enter_mainline("s6", "ops", cp) == SwitchState.MAINLINE


# --------------------------------------------------------------------------- #
# 哈希链冲突场景：乱序 / 跳号 / 空账本 / 重复 K 标
# --------------------------------------------------------------------------- #

def test_empty_ledger_verifies_ok():
    """空账本也是合法链。"""
    ledger = KMarkerLedger()
    assert ledger.verify_chain() is True
    assert len(ledger) == 0


def test_single_marker_chain_is_valid():
    ledger = KMarkerLedger()
    gov = SwitchbackGovernor(ledger=ledger)
    gov.admit("k1", "task", Grade.GENTLE)
    gov.seal("k1", "K0", {"x": 1})
    assert ledger.verify_chain()
    assert ledger.last_km_for("k1") == 0


def test_tampering_payload_breaks_chain():
    """篡改 payload 使后续断链。"""
    gov = SwitchbackGovernor()
    gov.admit("k2", "task", Grade.GENTLE)
    gov.seal("k2", "K0", {"x": 1})
    gov.seal("k2", "K1", {"x": 2})
    gov.seal("k2", "K2", {"x": 3})
    gov.ledger.entries()[0].payload["x"] = 999  # 篡改最早的
    with pytest.raises(LedgerIntegrityError):
        gov.ledger.verify_chain()


def test_tampering_sha256_directly_breaks_chain():
    """直接改 sha256 字段也断链。"""
    gov = SwitchbackGovernor()
    gov.admit("k3", "task", Grade.GENTLE)
    gov.seal("k3", "K0", {"x": 1})
    gov.ledger.entries()[0].sha256 = "0" * 64  # 伪造
    with pytest.raises(LedgerIntegrityError):
        gov.ledger.verify_chain()


def test_tampering_prev_link_breaks_chain():
    """改 prev_sha 链接断链。"""
    gov = SwitchbackGovernor()
    gov.admit("k4", "task", Grade.GENTLE)
    gov.seal("k4", "K0", {"x": 1})
    gov.seal("k4", "K1", {"x": 2})
    gov.ledger.entries()[1].prev_sha = "deadbeef"
    with pytest.raises(LedgerIntegrityError):
        gov.ledger.verify_chain()


def test_persistence_roundtrip_preserves_chain():
    """账本存盘再读回，链与内容一致。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "ledger.json")
        gov = SwitchbackGovernor(ledger=KMarkerLedger(path))
        gov.admit("k5", "task", Grade.STEEP)
        gov.seal("k5", "K0", {"a": 1})
        gov.seal("k5", "K1", {"a": 2})
        # 重新加载
        ledger2 = KMarkerLedger(path)
        assert len(ledger2) == 2
        assert ledger2.verify_chain()
        assert ledger2.last_km_for("k5") == 1


# --------------------------------------------------------------------------- #
# 任务卡持久化往返（CLI 多进程场景）
# --------------------------------------------------------------------------- #

def test_task_persistence_roundtrip():
    """admit → 持久化 → 新实例重载 → status 一致。"""
    with tempfile.TemporaryDirectory() as tmp:
        tpath = str(Path(tmp) / "tasks.json")
        gov1 = SwitchbackGovernor(tasks_path=tpath)
        gov1.admit("p1", "task A", Grade.STEEP)
        gov1.switch("p1", SwitchState.MAINLINE, actor="a", reason="release")
        gov1.pull_into_depot("p1", actor="safety", reason="incident")

        # 新实例（模拟 CLI 新进程）从磁盘重载
        gov2 = SwitchbackGovernor(tasks_path=tpath)
        st = gov2.status("p1")
        assert st["task"]["state"] == SwitchState.DEPOT.value
        assert st["task"]["grade"] == "steep"
        # ever_mainline 已重载 → 禁止自动恢复仍生效
        with pytest.raises(NoAutoResumeError):
            gov2.switch("p1", SwitchState.MAINLINE, actor="x")


def test_task_card_serialization_roundtrip():
    """TaskCard.to_dict 可往返，不丢字段。"""
    card = TaskCard(task_id="x", title="t", grade=Grade.MEDIUM, owner="me")
    d = card.to_dict()
    assert d["task_id"] == "x"
    assert d["grade"] == "medium"
    assert d["state"] == "depot"  # 默认入段开始


# --------------------------------------------------------------------------- #
# 运维第二案例端到端
# --------------------------------------------------------------------------- #

def test_ops_case_replay():
    from switchback.cases.ops import run_ops_case
    with tempfile.TemporaryDirectory() as tmp:
        summary = run_ops_case(ws=Path(tmp), headless=True)

    verdicts = {r["stage"]: r["verdict"] for r in summary["stages"]}
    # fix-v1 因回滚风险被否决折返；其余放行
    assert verdicts["fix-v1"] == "TURNED_BACK"
    assert verdicts["fix-v2"] == "RELEASED"
    assert verdicts["recovery-verify"] == "RELEASED"
    assert verdicts["postmortem"] == "RELEASED"
    assert summary["chain_integrity"] is True
    assert summary["turned_back"] == 1
    assert summary["released"] == 4
    assert summary["risks"] >= 3
