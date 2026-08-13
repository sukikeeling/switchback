"""Core protocol types of the Switchback Governance layer.

All types are stdlib-only dataclasses so the package runs anywhere with zero
dependencies. The vocabulary maps 1:1 onto the Jingzhang railway metaphor:

    Grade        -> 坡度分级   gentle / medium / steep
    SwitchState  -> 道岔三态   mainline / siding / depot
    Verdict      -> 折返点裁决 pass / turn_back / depot
    KMarker      -> K标版本    immutable, content-addressed, hash-chained
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# 基础枚举
# --------------------------------------------------------------------------- #

class Grade(str, Enum):
    """坡度分级准入（Grade-based Access）.

    Grade is assigned once, at task admission, by the grade-access skill.
    Higher grades face stricter review at every checkpoint.
    """

    GENTLE = "gentle"   # 缓坡：普惠/常规任务，单一责任人复核即可
    MEDIUM = "medium"   # 中坡：行业验证类任务，需专业预审
    STEEP = "steep"     # 陡坡：高影响/攻坚类任务，需三方联合复核


class SwitchState(str, Enum):
    """道岔三态（Switch States）—— 任务运行状态，不设自动恢复."""

    MAINLINE = "mainline"   # 正线运行
    SIDING = "siding"       # 侧线折返（被否决后退回返工）
    DEPOT = "depot"         # 入段检修（安全隔离；回正线须重新评估）


class Verdict(str, Enum):
    """折返点裁决."""

    PASS = "pass"           # 放行，继续沿正线
    TURN_BACK = "turn_back" # 折返，退回重做（强制）
    DEPOT = "depot"         # 入段，安全隔离（强制）


class PartyRole(str, Enum):
    """三方复核角色."""

    OWNER = "owner"             # 场景责任人（决策）
    PROFESSIONAL = "professional"  # 专业复核（技术）
    PUBLIC = "public"           # 公众/用户代表（权益）


class CheckpointKind(str, Enum):
    """折返点类型."""

    ADMISSION = "admission"           # 任务接单/准入
    PRE_VERIFY = "pre_verify"         # 结果验证前
    POST_VERIFY = "post_verify"       # 结果验证后
    EVIDENCE = "evidence"             # 执行证据沉淀
    APPROVAL = "approval"             # 审批（三方复核）
    RELEASE = "release"               # 发布/放行


# --------------------------------------------------------------------------- #
# 领域错误
# --------------------------------------------------------------------------- #

class SwitchbackError(Exception):
    """Base error for the Switchback Governance layer."""


class GradeAccessError(SwitchbackError):
    """坡度分级准入被拒绝."""


class NoAutoResumeError(SwitchbackError):
    """试图自动恢复 —— 折返治理不设自动恢复，必须显式人工裁决."""


class LedgerIntegrityError(SwitchbackError):
    """K标账本哈希链校验失败."""


# --------------------------------------------------------------------------- #
# 数据对象
# --------------------------------------------------------------------------- #

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(payload: dict[str, Any]) -> str:
    """Content-addressed SHA-256 over the canonical JSON payload."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class PartyVote:
    """单方复核意见."""

    role: PartyRole
    name: str
    verdict: Verdict
    note: str = ""
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "name": self.name,
            "verdict": self.verdict.value,
            "note": self.note,
            "timestamp": self.timestamp,
        }


@dataclass
class Checkpoint:
    """折返点（Switchback Node）—— 任务管线上的固定检查点."""

    kind: CheckpointKind
    task_id: str
    grade: Grade
    required_roles: list[PartyRole]
    votes: list[PartyVote] = field(default_factory=list)
    decided: Optional[Verdict] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def is_decided(self) -> bool:
        return self.decided is not None

    @property
    def vetoed(self) -> bool:
        """任何一方否决即强制折返."""
        return any(v.verdict in (Verdict.TURN_BACK, Verdict.DEPOT) for v in self.votes)

    def add_vote(self, vote: PartyVote) -> None:
        if self.is_decided:
            raise SwitchbackError(f"checkpoint {self.id} already decided")
        if any(v.role == vote.role for v in self.votes):
            raise SwitchbackError(f"role {vote.role.value} already voted")
        self.votes.append(vote)

    def resolve(self) -> Verdict:
        """All required roles must vote. Any veto => TURN_BACK (强制折返).

        Returns PASS only when every required role voted PASS.
        No auto-recovery: the caller decides what happens next, never the checkpoint.
        """
        voted_roles = {v.role for v in self.votes}
        missing = [r for r in self.required_roles if r not in voted_roles]
        if missing:
            raise SwitchbackError(
                f"checkpoint {self.id} missing votes from: {[r.value for r in missing]}"
            )
        if self.vetoed:
            # 默认折返；若存在 DEPOT 票则入段（更安全的一票）
            self.decided = Verdict.DEPOT if any(
                v.verdict == Verdict.DEPOT for v in self.votes
            ) else Verdict.TURN_BACK
        else:
            self.decided = Verdict.PASS
        return self.decided

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "task_id": self.task_id,
            "grade": self.grade.value,
            "required_roles": [r.value for r in self.required_roles],
            "votes": [v.to_dict() for v in self.votes],
            "decided": self.decided.value if self.decided else None,
        }


@dataclass
class KMarker:
    """K标版本 —— 每次数据更新/复算/放行记入一个新的 K 标."""

    km: int
    task_id: str
    label: str
    payload: dict[str, Any]
    sha256: str = ""
    prev_sha: str = ""
    timestamp: str = field(default_factory=_now)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def seal(self, prev_sha: str = "") -> "KMarker":
        """Compute the content-addressed digest and link to the previous marker."""
        self.prev_sha = prev_sha
        body = {
            "km": self.km,
            "task_id": self.task_id,
            "label": self.label,
            "payload": self.payload,
            "prev_sha": self.prev_sha,
            "timestamp": self.timestamp,
        }
        self.sha256 = _digest(body)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "km": self.km,
            "id": self.id,
            "task_id": self.task_id,
            "label": self.label,
            "payload": self.payload,
            "prev_sha": self.prev_sha,
            "sha256": self.sha256,
            "timestamp": self.timestamp,
        }


@dataclass
class TaskCard:
    """任务卡 —— 折返治理管线的运行单元."""

    task_id: str
    title: str
    grade: Grade
    owner: str = "agent-manager"
    state: SwitchState = SwitchState.DEPOT  # 一律入段开始，经准入后上正线
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "grade": self.grade.value,
            "owner": self.owner,
            "state": self.state.value,
            "created_at": self.created_at,
        }
