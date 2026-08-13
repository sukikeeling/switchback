"""Tests for the core protocol: grades, checkpoints, vetoes, no-auto-resume."""

import pytest

from switchback.governor import SwitchbackGovernor
from switchback.protocol import (
    CheckpointKind,
    Grade,
    LedgerIntegrityError,
    NoAutoResumeError,
    PartyRole,
    SwitchState,
    SwitchbackError,
    Verdict,
)


def _gov():
    return SwitchbackGovernor()


# --------------------------------------------------------------------------- #
# 坡度分级准入
# --------------------------------------------------------------------------- #

def test_admit_assigns_grade_and_starts_in_depot():
    gov = _gov()
    card = gov.admit("t1", "demo task", Grade.STEEP)
    assert card.grade == Grade.STEEP
    assert card.state == SwitchState.DEPOT  # 一律入段开始，经准入后上正线


def test_grade_maps_to_required_roles():
    gov = _gov()
    assert gov.required_roles(Grade.GENTLE) == [PartyRole.OWNER]
    assert gov.required_roles(Grade.MEDIUM) == [PartyRole.OWNER, PartyRole.PROFESSIONAL]
    assert gov.required_roles(Grade.STEEP) == [PartyRole.OWNER, PartyRole.PROFESSIONAL, PartyRole.PUBLIC]


def test_steep_requires_extra_checkpoints_in_policy():
    gov = _gov()
    extra = gov.policy["checkpoints"]["steep_extra"]
    assert "pre_verify" in extra
    assert "evidence" in extra


# --------------------------------------------------------------------------- #
# 折返点裁决
# --------------------------------------------------------------------------- #

def test_any_single_veto_forces_turn_back():
    gov = _gov()
    gov.admit("t2", "steep task", Grade.STEEP)
    cp = gov.open_checkpoint("t2", CheckpointKind.APPROVAL)
    gov.vote(cp, PartyRole.OWNER, "owner", Verdict.PASS)
    gov.vote(cp, PartyRole.PROFESSIONAL, "prof", Verdict.PASS)
    gov.vote(cp, PartyRole.PUBLIC, "public", Verdict.TURN_BACK, note="权益风险")  # 唯一否决
    assert cp.resolve() == Verdict.TURN_BACK


def test_all_pass_releases():
    gov = _gov()
    gov.admit("t3", "steep task", Grade.STEEP)
    cp = gov.open_checkpoint("t3", CheckpointKind.APPROVAL)
    for role in (PartyRole.OWNER, PartyRole.PROFESSIONAL, PartyRole.PUBLIC):
        gov.vote(cp, role, role.value, Verdict.PASS)
    assert cp.resolve() == Verdict.PASS


def test_depot_vote_is_safer_than_turn_back():
    gov = _gov()
    gov.admit("t4", "steep task", Grade.STEEP)
    cp = gov.open_checkpoint("t4", CheckpointKind.APPROVAL)
    gov.vote(cp, PartyRole.OWNER, "owner", Verdict.DEPOT)   # 入段（更安全的一票）
    gov.vote(cp, PartyRole.PROFESSIONAL, "prof", Verdict.PASS)
    gov.vote(cp, PartyRole.PUBLIC, "public", Verdict.PASS)
    assert cp.resolve() == Verdict.DEPOT


def test_resolve_requires_all_roles():
    gov = _gov()
    gov.admit("t5", "steep task", Grade.STEEP)
    cp = gov.open_checkpoint("t5", CheckpointKind.APPROVAL)
    gov.vote(cp, PartyRole.OWNER, "owner", Verdict.PASS)
    with pytest.raises(SwitchbackError):
        cp.resolve()  # professional + public 未投票


def test_double_vote_rejected():
    gov = _gov()
    gov.admit("t6", "task", Grade.GENTLE)
    cp = gov.open_checkpoint("t6", CheckpointKind.APPROVAL)
    gov.vote(cp, PartyRole.OWNER, "owner", Verdict.PASS)
    with pytest.raises(SwitchbackError):
        gov.vote(cp, PartyRole.OWNER, "owner", Verdict.PASS)


# --------------------------------------------------------------------------- #
# 道岔三态：不设自动恢复
# --------------------------------------------------------------------------- #

def test_no_auto_resume_from_depot():
    gov = _gov()
    gov.admit("t7", "task", Grade.MEDIUM)
    gov.switch("t7", SwitchState.MAINLINE, actor="approver", reason="first release")  # 首次放行
    gov.pull_into_depot("t7", actor="safety", reason="test")
    with pytest.raises(NoAutoResumeError):
        gov.switch("t7", SwitchState.MAINLINE, actor="anything")  # 已被放行又入段 => 禁止自动恢复


def test_first_admission_to_mainline_is_allowed():
    gov = _gov()
    gov.admit("t7b", "task", Grade.GENTLE)
    # 首次准入上正线（经准入闸门）是受允许的，不算"自动恢复"
    assert gov.switch("t7b", SwitchState.MAINLINE, actor="approver", reason="admission") == SwitchState.MAINLINE


def test_reeenter_mainline_requires_fresh_approval():
    gov = _gov()
    gov.admit("t8", "task", Grade.MEDIUM)
    gov.pull_into_depot("t8")
    cp = gov.open_checkpoint("t8", CheckpointKind.APPROVAL)
    # 重新评估：未通过则不能回正线
    gov.vote(cp, PartyRole.OWNER, "owner", Verdict.PASS)
    with pytest.raises(SwitchbackError):
        gov.re_enter_mainline("t8", "operator", cp)  # 还缺 professional
    gov.vote(cp, PartyRole.PROFESSIONAL, "prof", Verdict.PASS)
    cp.resolve()
    assert gov.re_enter_mainline("t8", "operator", cp) == SwitchState.MAINLINE


def test_turn_back_moves_to_siding():
    gov = _gov()
    gov.admit("t9", "task", Grade.GENTLE)
    gov.turn_back("t9", actor="verifier", reason="rework")
    assert gov.status("t9")["task"]["state"] == SwitchState.SIDING


# --------------------------------------------------------------------------- #
# K标账本
# --------------------------------------------------------------------------- #

def test_ledger_seals_and_verifies_chain():
    gov = _gov()
    gov.admit("t10", "task", Grade.GENTLE)
    m1 = gov.seal("t10", "K0 admission", {"a": 1})
    m2 = gov.seal("t10", "K-release", {"a": 2})
    assert m1.km == 0 and m2.km == 1
    assert m2.prev_sha == m1.sha256
    assert gov.ledger.verify_chain()


def test_tampering_breaks_chain():
    gov = _gov()
    gov.admit("t11", "task", Grade.GENTLE)
    gov.seal("t11", "K0", {"a": 1})
    gov.seal("t11", "K1", {"a": 2})
    # 篡改中间条目
    entry = gov.ledger.entries()[0]
    entry.payload["a"] = 999
    with pytest.raises(LedgerIntegrityError):
        gov.ledger.verify_chain()
