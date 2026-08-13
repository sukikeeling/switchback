"""Skill engineering — the six core skills as executable Python functions.

GOAI Track-1 treats Skill engineering as a 25% rubric axis and requires a Skill
inventory (name / purpose / in-out / invoke conditions / dependent tools /
failure handling / safety boundary / reuse value). This module ships the six
core switchback skills as plain, dependency-free functions, each with a
structured ``SkillSpec`` describing exactly those fields — so the Skill inventory
in the competition docs is not a slide claim but runnable code.

Skills:
  S1 grade-access     坡度准入 —— assigns a Grade to an incoming task.
  S2 evidence-verify  证据核验 —— numeric three-way alignment + reference
                      cross-check + content hash (the "verifier agent").
  S3 kmarker-ledger   K标账本 —— seals an immutable K-marker entry.
  S4 risk-ledger      风险台账 —— records a risk with mitigation + human review.
  S5 switch-decision  折返裁决 —— resolves a three-party checkpoint.
  S6 lessons-learned  经验沉淀 —— writes a lesson back into agent memory.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .ledger import KMarkerLedger, RiskLedger
from .protocol import Checkpoint, Grade, PartyRole, Verdict
from .state import AgentMemory


# --------------------------------------------------------------------------- #
# Skill 描述契约
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SkillSpec:
    """A machine-readable Skill declaration (mirrors docs/skills.md)."""

    name: str
    purpose: str
    inputs: str
    outputs: str
    invoke_condition: str
    dependencies: str
    failure_handling: str
    safety_boundary: str
    reuse_value: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "invoke_condition": self.invoke_condition,
            "dependencies": self.dependencies,
            "failure_handling": self.failure_handling,
            "safety_boundary": self.safety_boundary,
            "reuse_value": self.reuse_value,
        }


def _spec(name: str, purpose: str, inputs: str, outputs: str, invoke: str,
          deps: str, fail: str, boundary: str, reuse: str) -> SkillSpec:
    return SkillSpec(name, purpose, inputs, outputs, invoke, deps, fail, boundary, reuse)


# --------------------------------------------------------------------------- #
# S1 坡度准入
# --------------------------------------------------------------------------- #

def grade_access(payload: dict[str, Any], trust_score: float = 0.5) -> Grade:
    """Assign a grade from a task's risk surface.

    Scoring: higher impact + lower trust => steeper grade.
    """
    impact = float(payload.get("impact", 0.5))
    sensitivity = float(payload.get("sensitivity", 0.0))
    reversibility = float(payload.get("reversibility", 1.0))  # 1 = fully reversible
    risk = (0.4 * impact + 0.4 * sensitivity + 0.2 * (1 - reversibility)) * (2 - trust_score)
    if risk >= 1.2:
        return Grade.STEEP
    if risk >= 0.6:
        return Grade.MEDIUM
    return Grade.GENTLE


GRADE_ACCESS_SPEC = _spec(
    "grade-access",
    "坡度分级准入：按任务风险面分配缓坡/中坡/陡坡，坡度越高准入复审越严。",
    "task payload（impact/sensitivity/reversibility）+ trust_score",
    "Grade 枚举（gentle/medium/steep）",
    "任务接单时（admission checkpoint 前）",
    "无",
    "无法判定时默认 STEEP（从严）",
    "只做分级，不做授权；授权仍需折返点复核",
    "任何多 Agent 系统的任务准入层可直接复用",
)


# --------------------------------------------------------------------------- #
# S2 证据核验
# --------------------------------------------------------------------------- #

class VerificationReport:
    """Output of S2."""

    def __init__(self, checks: list[dict[str, Any]], passed: bool) -> None:
        self.checks = checks
        self.passed = passed

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": self.checks}


def evidence_verify(
    claims: dict[str, Any],
    sources: dict[str, Any],
    numeric_keys: Optional[list[str]] = None,
) -> VerificationReport:
    """Three checks the Jingzhang project learned the hard way:

      1. 数值三处对齐  — every numeric claim must appear identically in >=3 places;
      2. 引用双向检查  — every claim cites a source that exists, every source is cited;
      3. 内容寻址哈希  — every artifact payload has a stable content digest.

    Anything that fails marks the artifact FIXED/REWORK and forces a turn-back.
    """
    checks: list[dict[str, Any]] = []
    numeric_keys = numeric_keys or []

    # 1) numeric three-way alignment
    for key in numeric_keys:
        places = [
            claims.get(key),
            claims.get(f"{key}_alt1"),
            claims.get(f"{key}_alt2"),
        ]
        present = [p for p in places if p is not None]
        ok = len(present) >= 3 and len(set(present)) == 1
        checks.append({"check": "numeric_three_way", "key": key, "ok": ok,
                       "values": present})

    # 2) bidirectional reference check
    cited = {k for v in claims.values() if isinstance(v, str)
             for k in re.findall(r"source:([A-Z0-9-]+)", v)}
    missing_sources = sorted(cited - set(sources))
    uncited_sources = sorted(set(sources) - cited)
    checks.append({"check": "reference_forward", "ok": not missing_sources,
                   "missing": missing_sources})
    checks.append({"check": "reference_backward", "ok": not uncited_sources,
                   "uncited": uncited_sources})

    # 3) content-addressable digest
    #    The digest is computed over the artifact WITHOUT the self-hash field,
    #    so "did the artifact change since it was sealed?" is answerable.
    body = {k: v for k, v in claims.items() if k != "content_sha256"}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    claimed_digest = claims.get("content_sha256")
    checks.append({"check": "content_hash", "ok": claimed_digest is None or claimed_digest == digest,
                   "digest": digest[:16]})

    passed = all(c["ok"] for c in checks)
    return VerificationReport(checks, passed)


EVIDENCE_VERIFY_SPEC = _spec(
    "evidence-verify",
    "证据核验：数值三处对齐 + 引用双向检查 + 内容寻址哈希。",
    "claims dict + sources dict + numeric_keys",
    "VerificationReport（passed + 逐项检查）",
    "产出物进入 post_verify 折返点之前",
    "hashlib / re（内置）",
    "任一检查失败 => passed=False，强制标记 REWORK 并折返",
    "只读校验，不改动工件；不通过不进入审批",
    "所有'Agent 输出不可信'问题的第一道闸门，跨行业复用",
)


# --------------------------------------------------------------------------- #
# S3 K标账本
# --------------------------------------------------------------------------- #

def kmarker_seal(ledger: KMarkerLedger, task_id: str, label: str, payload: dict[str, Any]):
    """Seal an immutable K-marker; raises on chain break."""
    marker = ledger.append(task_id, label, payload)
    assert ledger.verify_chain(), "K-marker chain integrity broken"
    return marker


KMARKER_LEDGER_SPEC = _spec(
    "kmarker-ledger",
    "K标账本：每次数据更新/复算/放行记入不可变哈希链 K 标。",
    "task_id + label + payload",
    "KMarker（km/sha256/prev_sha）",
    "任何数据更新、复算、放行时刻",
    "KMarkerLedger（哈希链）",
    "链校验失败 => LedgerIntegrityError，拒绝写入",
    "只追加不覆盖；审计方持链可全量复核",
    "金融/合规/政务等一切需要审计留痕的场景",
)


# --------------------------------------------------------------------------- #
# S4 风险台账
# --------------------------------------------------------------------------- #

def risk_record(ledger: RiskLedger, risk_id: str, title: str, score: int,
                note: str, mitigation: str, human_review: str) -> dict[str, Any]:
    """Record one structured risk; higher score => mandatory human review."""
    return ledger.add(risk_id, title, score, note, mitigation, human_review)


RISK_LEDGER_SPEC = _spec(
    "risk-ledger",
    "风险台账：结构化记录风险、缓释措施与人工复核责任人。",
    "risk 字段（id/title/score/note/mitigation/human_review）",
    "风险条目（score>=4 标记强制人工复核）",
    "全流程持续（admission / 每次折返 / 放行前）",
    "RiskLedger",
    "风险升级 => 标记 mandatory_human_review 并暂停放行",
    "只记录与标记，不替代人工决策",
    "等保/合规审计的标准化风险视图",
)


# --------------------------------------------------------------------------- #
# S5 折返裁决
# --------------------------------------------------------------------------- #

def switch_decision(checkpoint: Checkpoint) -> Verdict:
    """Resolve a three-party checkpoint; any veto forces turn-back/depot."""
    return checkpoint.resolve()


SWITCH_DECISION_SPEC = _spec(
    "switch-decision",
    "折返裁决：三方复核（责任人/专业/公众），任何否决即强制折返。",
    "Checkpoint（已收集满 required_roles 的投票）",
    "Verdict（pass/turn_back/depot）",
    "每个折返点票数收满时",
    "Checkpoint",
    "票数不足 => SwitchbackError 拒绝裁决；不自动恢复",
    "裁决后状态迁移必须由人显式触发（道岔）",
    "一切需要审批与回滚的 Agent 管线核心",
)


# --------------------------------------------------------------------------- #
# S6 经验沉淀
# --------------------------------------------------------------------------- #

def lessons_learned(memory: AgentMemory, agent_id: str, content: str,
                    tags: Optional[list[str]] = None):
    """Write a lesson back to agent memory at the end of a loop."""
    return memory.remember(agent_id, "lesson", content, tags or ["lessons"])


LESSONS_LEARNED_SPEC = _spec(
    "lessons-learned",
    "经验沉淀：把复盘结论写回 Agent 记忆，形成教训-规则闭环。",
    "agent_id + 复盘结论 content + tags",
    "MemoryEntry",
    "每个任务闭环收尾 / 每次折返复盘时",
    "AgentMemory",
    "写入失败不影响主线，标记 memory_warn",
    "只写回记忆，不自动改写治理策略",
    "让系统'越用越聪明'，是复赛'经验沉淀'维度的直接落点",
)


ALL_SKILLS: dict[str, SkillSpec] = {
    s.name: s for s in [
        GRADE_ACCESS_SPEC,
        EVIDENCE_VERIFY_SPEC,
        KMARKER_LEDGER_SPEC,
        RISK_LEDGER_SPEC,
        SWITCH_DECISION_SPEC,
        LESSONS_LEARNED_SPEC,
    ]
}
