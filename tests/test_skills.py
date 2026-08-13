"""Tests for the six core skills."""

from switchback.ledger import KMarkerLedger, RiskLedger
from switchback.protocol import CheckpointKind, Grade, PartyRole, Verdict
from switchback.skills import ALL_SKILLS, evidence_verify, grade_access, kmarker_seal, switch_decision
from switchback.state import AgentMemory
from switchback.governor import SwitchbackGovernor


# --------------------------------------------------------------------------- #
# S1 坡度准入
# --------------------------------------------------------------------------- #

def test_grade_access_maps_risk_to_grade():
    assert grade_access(dict(impact=0.9, sensitivity=0.9, reversibility=0.0), trust_score=0.2) == Grade.STEEP
    assert grade_access(dict(impact=0.2, sensitivity=0.1, reversibility=1.0), trust_score=0.9) == Grade.GENTLE
    # 无法判定时不得低于 medium 从严：极高信任低风险为 gentle 可接受
    assert grade_access(dict(impact=0.5, sensitivity=0.3, reversibility=0.8), trust_score=0.7) in (
        Grade.GENTLE, Grade.MEDIUM
    )


# --------------------------------------------------------------------------- #
# S2 证据核验
# --------------------------------------------------------------------------- #

def test_evidence_verify_numeric_three_way():
    claims = {"score": 84, "score_alt1": 84, "score_alt2": 84, "cite": "source:S1"}
    report = evidence_verify(claims, {"S1": "doc"}, numeric_keys=["score"])
    assert report.passed


def test_evidence_verify_content_hash_detects_tampering():
    claims = {"score": 84, "content_sha256": "0" * 64}  # 声明了错误哈希
    report = evidence_verify(claims, {"S1": "doc"}, numeric_keys=[])
    assert not report.passed  # 声明哈希与内容不符 => 篡改报警


def test_evidence_verify_flags_misalignment():
    claims = {"score": 84, "score_alt1": 84, "score_alt2": 70, "content_sha256": "x"}
    report = evidence_verify(claims, {"S1": "doc"}, numeric_keys=["score"])
    assert not report.passed  # 数值三处不齐 => 强制折返


def test_evidence_verify_reference_bidirectional():
    claims = {"cite": "source:OFFICIAL"}
    report = evidence_verify(claims, {"OFFICIAL": "doc", "UNUSED": "doc"})
    assert not report.passed  # UNUSED 未被引用 + OFFICIAL 存在 => 反向检查失败
    claims2 = {"cite": "source:OFFICIAL"}
    report2 = evidence_verify(claims2, {"OFFICIAL": "doc"})
    assert report2.passed


def test_all_six_skill_specs_are_complete():
    required_fields = {"name", "purpose", "inputs", "outputs", "invoke_condition",
                       "dependencies", "failure_handling", "safety_boundary", "reuse_value"}
    assert len(ALL_SKILLS) == 6
    for spec in ALL_SKILLS.values():
        assert required_fields.issubset(set(spec.to_dict()))
        assert all(spec.to_dict()[f] for f in required_fields)  # 非空


# --------------------------------------------------------------------------- #
# S3/S5 组合
# --------------------------------------------------------------------------- #

def test_skill_compose_with_governor():
    gov = SwitchbackGovernor(ledger=KMarkerLedger())
    gov.admit("t", "task", Grade.STEEP)
    kmarker_seal(gov.ledger, "t", "K0", {"v": 1})
    assert gov.ledger.verify_chain()

    cp = gov.open_checkpoint("t", CheckpointKind.APPROVAL)
    for role in (PartyRole.OWNER, PartyRole.PROFESSIONAL, PartyRole.PUBLIC):
        gov.vote(cp, role, role.value, Verdict.PASS)
    assert switch_decision(cp) == Verdict.PASS


def test_risk_and_memory_seed_rag():
    risk = RiskLedger()
    risk.add("r1", "幻觉", 4, "note", "mitigation", "human")
    assert risk.highest()[0]["flag"] == "mandatory_human_review"

    memory = AgentMemory()
    memory.remember("w-verify", "lesson", "数值必须三处对齐", tags=["evidence"])
    assert memory.recall("数值")[0].content == "数值必须三处对齐"
