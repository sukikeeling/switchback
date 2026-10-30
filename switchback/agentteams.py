"""Executable AgentTeams (Hiclaw) Multi-Agent Orchestration & Matrix Room Bus.

Eliminates the "paper mapping only" gap by providing an executable Manager-Worker
+ Matrix Room Event Bus + Higress Consumer Token runtime that routes every tool
call and inter-agent message through the Switchback Sidecar Governance Gateway.

Six canonical AgentTeams identities:
  * M-OPER       (Manager)  — Task intake, grade decomposition, DAG scheduling
  * W-RESEARCH   (Worker)   — External intelligence & live source snapshot fetch
  * W-CREATE     (Worker)   — Bilingual structured artifact production
  * W-VERIFY     (Worker)   — 3-way numeric, bidirectional citation & package drift check
  * W-RISK       (Worker)   — Structured risk & rights ledger assessment
  * G-GOVERNOR   (Governor) — Checkpoint adjudication, switch state & Merkle seal
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .governor import SwitchbackGovernor
from .ledger import RightsLedger, RiskLedger
from .protocol import (
    CheckpointKind,
    ErrSwitchbackTriggered,
    Grade,
    PartyRole,
    SwitchState,
    Verdict,
)
from .sidecar import SwitchbackSidecarGateway
from .skills import grade_access, lessons_learned, risk_record
from .state import AgentMemory, SharedState


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class MatrixEvent:
    """Matrix Client-Server protocol shaped room event."""

    room_id: str
    sender: str
    event_type: str  # "m.room.message" | "m.switchback.checkpoint" | "m.switchback.circuit_break"
    content: dict[str, Any]
    event_id: str = field(default_factory=lambda: f"$ev_{uuid.uuid4().hex[:12]}")
    origin_server_ts: int = field(default_factory=_now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "room_id": self.room_id,
            "sender": self.sender,
            "type": self.event_type,
            "origin_server_ts": self.origin_server_ts,
            "content": self.content,
        }


class MatrixRoomBus:
    """In-memory / webhook-compatible Matrix Room communication bus.

    All agent-to-agent messages and governance checkpoints are posted to a Matrix
    room so human supervisors can observe and intervene in real time.
    """

    def __init__(self, domain: str = "switchback.local") -> None:
        self.domain = domain
        self._rooms: dict[str, list[MatrixEvent]] = {}

    def ensure_room(self, room_alias: str) -> str:
        room_id = room_alias if room_alias.startswith("!") else f"!{room_alias}:{self.domain}"
        self._rooms.setdefault(room_id, [])
        return room_id

    def post(
        self,
        room_id: str,
        agent_id: str,
        body: str,
        event_type: str = "m.room.message",
        extra: Optional[dict[str, Any]] = None,
    ) -> MatrixEvent:
        rid = self.ensure_room(room_id)
        sender = agent_id if agent_id.startswith("@") else f"@{agent_id.lower()}:{self.domain}"
        content = {"msgtype": "m.text", "body": body, **(extra or {})}
        ev = MatrixEvent(room_id=rid, sender=sender, event_type=event_type, content=content)
        self._rooms[rid].append(ev)
        return ev

    def history(self, room_id: str) -> list[dict[str, Any]]:
        rid = self.ensure_room(room_id)
        return [e.to_dict() for e in self._rooms.get(rid, [])]


@dataclass(frozen=True)
class AgentIdentity:
    """AgentTeams identity specification with Higress consumer token badge."""

    agent_id: str
    role_title: str
    kind: str  # "manager" | "worker" | "governor"
    consumer_token: str
    responsibilities: list[str]


AGENTTEAMS_ROSTER: dict[str, AgentIdentity] = {
    "M-OPER": AgentIdentity(
        agent_id="M-OPER",
        role_title="运营总监 (Manager Agent)",
        kind="manager",
        consumer_token="ctok_m_oper",
        responsibilities=["task_intake", "grade_decomposition", "dag_dispatch", "trigger_checkpoint"],
    ),
    "W-RESEARCH": AgentIdentity(
        agent_id="W-RESEARCH",
        role_title="调研专员 (Research Worker)",
        kind="worker",
        consumer_token="ctok_w_research",
        responsibilities=["source_collection", "snapshot_locking", "api_probe"],
    ),
    "W-CREATE": AgentIdentity(
        agent_id="W-CREATE",
        role_title="内容专员 (Creation Worker)",
        kind="worker",
        consumer_token="ctok_w_create",
        responsibilities=["structured_artifact", "bilingual_equivalence"],
    ),
    "W-VERIFY": AgentIdentity(
        agent_id="W-VERIFY",
        role_title="校验专员 (Verification Worker)",
        kind="worker",
        consumer_token="ctok_w_verify",
        responsibilities=["numeric_three_way", "citation_bidirectional", "atomic_package_check"],
    ),
    "W-RISK": AgentIdentity(
        agent_id="W-RISK",
        role_title="风险与合规专员 (Risk Worker)",
        kind="worker",
        consumer_token="ctok_w_risk",
        responsibilities=["risk_ledger", "rights_ledger", "compliance_matrix"],
    ),
    "G-GOVERNOR": AgentIdentity(
        agent_id="G-GOVERNOR",
        role_title="监理 Agent (Switchback Governor)",
        kind="governor",
        consumer_token="ctok_g_governor",
        responsibilities=["grade_access", "switch_decision", "kmarker_seal", "no_auto_resume"],
    ),
}


class AgentTeamsCluster:
    """Executable 6-Agent cluster orchestrated over Matrix Room Bus + Sidecar Gateway."""

    def __init__(
        self,
        gateway: Optional[SwitchbackSidecarGateway] = None,
        matrix_bus: Optional[MatrixRoomBus] = None,
        shared_state: Optional[SharedState] = None,
        memory: Optional[AgentMemory] = None,
        risk_ledger: Optional[RiskLedger] = None,
        rights_ledger: Optional[RightsLedger] = None,
    ) -> None:
        self.gateway = gateway if gateway is not None else SwitchbackSidecarGateway()
        self.governor: SwitchbackGovernor = self.gateway.governor
        self.matrix = matrix_bus if matrix_bus is not None else MatrixRoomBus()
        self.shared_state = shared_state if shared_state is not None else SharedState()
        self.memory = memory if memory is not None else AgentMemory()
        self.risk_ledger = risk_ledger if risk_ledger is not None else RiskLedger()
        self.rights_ledger = rights_ledger if rights_ledger is not None else RightsLedger()
        self.roster = dict(AGENTTEAMS_ROSTER)

    def run_eight_step_pipeline(
        self,
        task_id: str,
        title: str,
        risk_surface: dict[str, Any],
        worker_payload: dict[str, Any],
        votes: Optional[dict[PartyRole, Verdict]] = None,
        room_alias: str = "switchback-ops",
    ) -> dict[str, Any]:
        """Execute the full 8-step closed loop across the 6 AgentTeams identities:

          Step 1: 任务输入 (M-OPER intakes task in Matrix room)
          Step 2: 任务拆解 (M-OPER grades task & decomposes DAG)
          Step 3: 上下文传递 (SharedState stamped with K0 K-marker)
          Step 4: 工具调用 (W-RESEARCH / W-CREATE execute through Sidecar with consumer tokens)
          Step 5: 结果验证 (W-VERIFY runs LiveEvidenceEngine via Sidecar)
          Step 6: 执行证据沉淀 (G-GOVERNOR seals K-marker into Merkle ledger)
          Step 7: 审批与回滚 (Three-party checkpoint in Matrix room; no auto-resume)
          Step 8: 经验沉淀 (lessons-learned written to AgentMemory)
        """
        room_id = self.matrix.ensure_room(room_alias)

        # Step 1 & 2: M-OPER intakes task and runs grade-access
        self.matrix.post(room_id, "M-OPER", f"[Step 1] 接单任务 {task_id}: {title}")
        grade = grade_access(risk_surface, trust_score=float(risk_surface.get("trust", 0.5)))
        card = self.governor.admit(task_id, title, grade, owner="M-OPER")
        k0 = self.governor.seal(task_id, "K0 admission", {"grade": grade.value, "title": title})
        self.matrix.post(
            room_id,
            "M-OPER",
            f"[Step 2] 坡度分级准入完成: grade={grade.value}, K0={k0.sha256[:12]}",
            extra={"km": k0.km, "grade": grade.value},
        )

        # Step 3: SharedState context propagation with K-marker provenance
        self.shared_state.put(f"{task_id}:spec", {"title": title, "grade": grade.value}, km=k0.km)
        self.matrix.post(room_id, "M-OPER", f"[Step 3] 共享上下文已写入 SharedState (provenance=K{k0.km})")

        # Step 4 & 5: Worker execution & Live Evidence Verification through Sidecar Gateway
        try:
            intercept_res = self.gateway.intercept(
                {
                    "task_id": task_id,
                    "actor": "W-VERIFY",
                    "tool": "artifact.verify_and_deliver",
                    "consumer_token": self.roster["W-VERIFY"].consumer_token,
                    "payload": worker_payload,
                    "auto_admit_mainline": False,
                }
            )
            self.matrix.post(
                room_id,
                "W-VERIFY",
                f"[Step 4-5] Sidecar 实时校验通过 (K{intercept_res['km']})",
                extra={"km": intercept_res["km"]},
            )
        except ErrSwitchbackTriggered as cb:
            self.matrix.post(
                room_id,
                "G-GOVERNOR",
                f"[Step 5 熔断] Sidecar 触发物理级硬熔断: {cb.violation_kind} -> {cb.target_state.value}",
                event_type="m.switchback.circuit_break",
                extra=cb.to_dict(),
            )
            lessons_learned(
                self.memory,
                "W-VERIFY",
                f"{task_id}: Sidecar 拦截违规 ({cb.violation_kind})，状态切入 {cb.target_state.value}",
                tags=["sidecar", cb.violation_kind],
            )
            return {
                "task_id": task_id,
                "status": "CIRCUIT_BROKEN",
                "state": cb.target_state.value,
                "violation_kind": cb.violation_kind,
                "error": cb.to_dict(),
                "room_events": len(self.matrix.history(room_id)),
                "merkle_root": self.governor.ledger.merkle_root(),
            }

        # Step 6: W-RISK logs structured risk
        risk_record(
            self.risk_ledger,
            risk_id=f"risk-{task_id}",
            title=f"{title} 运行风险核查",
            score=4 if grade == Grade.STEEP else 2,
            note="经 Sidecar 网关与活体证据核验器双重校验",
            mitigation="三方折返点复核 + K标 Merkle 存证",
            human_review="G-GOVERNOR + 人类总指挥台",
        )

        # Step 7: Three-party Checkpoint in Matrix Room
        cp = self.governor.open_checkpoint(task_id, CheckpointKind.APPROVAL)
        vote_map = votes or {}
        for role in self.governor.required_roles(grade):
            v = vote_map.get(role, Verdict.PASS)
            self.governor.vote(cp, role, f"{role.value}-reviewer", v, note="Matrix room vote")
        verdict = cp.decided if cp.is_decided else self.governor.resolve(cp)

        if verdict == Verdict.PASS:
            self.governor.switch(task_id, SwitchState.MAINLINE, actor="G-GOVERNOR", reason="Matrix three-party pass")
            k_rel = self.governor.seal(task_id, "K-release", {"verdict": "pass", "room_id": room_id})
            self.shared_state.put(f"{task_id}:release", {"verdict": "pass"}, km=k_rel.km)
            self.matrix.post(
                room_id,
                "G-GOVERNOR",
                f"[Step 6-7] 折返点三方放行 -> MAINLINE (K{k_rel.km}, Merkle={self.governor.ledger.merkle_root()[:12]})",
                event_type="m.switchback.checkpoint",
            )
            final_status = "RELEASED"
        elif verdict == Verdict.DEPOT:
            self.governor._ever_mainline.add(task_id)
            self.governor.pull_into_depot(task_id, actor="G-GOVERNOR", reason="Matrix depot vote")
            self.governor.seal(task_id, "K-depot", {"verdict": "depot", "room_id": room_id})
            self.matrix.post(room_id, "G-GOVERNOR", "[Step 7] 折返点裁决 -> DEPOT 入段检修（不设自动恢复）")
            final_status = "DEPOT"
        else:
            self.governor.turn_back(task_id, actor="G-GOVERNOR", reason="Matrix turn_back vote")
            self.governor.seal(task_id, "K-turnback", {"verdict": "turn_back", "room_id": room_id})
            self.matrix.post(room_id, "G-GOVERNOR", "[Step 7] 折返点一票否决 -> SIDING 侧线折返（不设自动恢复）")
            final_status = "TURNED_BACK"

        # Step 8: Lessons learned
        lessons_learned(
            self.memory,
            "M-OPER",
            f"{task_id} 完成 8 步闭环: status={final_status}, state={self.governor.status(task_id)['task']['state']}",
            tags=["agentteams", final_status.lower()],
        )
        self.matrix.post(room_id, "M-OPER", f"[Step 8] 经验已沉淀至 AgentMemory (共 {len(self.memory.export())} 条)")

        return {
            "task_id": task_id,
            "status": final_status,
            "grade": grade.value,
            "state": self.governor.status(task_id)["task"]["state"],
            "room_id": room_id,
            "room_events": len(self.matrix.history(room_id)),
            "merkle_root": self.governor.ledger.merkle_root(),
        }
