"""The Switchback Governor — a declarative rule engine over the protocol.

The Governor is the "监理 Agent" (G-GOVERNOR) of a multi-agent team. It owns:

  * **admission**   — grade-based access: steeper grades face stricter checks;
  * **checkpoints** — the switchback nodes on the pipeline;
  * **transitions** — the three switch states (mainline / siding / depot) with
                      **no automatic recovery**;
  * **K-markers**   — every release / recalc / data update seals a ledger entry.

Governance is declared in a policy (JSON), not hard-coded, so operators can tune
review depth per grade without touching the engine.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .ledger import KMarkerLedger
from .protocol import (
    Checkpoint,
    CheckpointKind,
    Grade,
    GradeAccessError,
    KMarker,
    NoAutoResumeError,
    PartyRole,
    PartyVote,
    SwitchState,
    SwitchbackError,
    TaskCard,
    Verdict,
)
from .trace import Tracer

# Policy defaults when no governance.json is supplied.
DEFAULT_POLICY: dict[str, Any] = {
    "schema_version": "1.0",
    "admission": {
        "gentle": {"requires": ["owner"], "min_knowledge": "basic"},
        "medium": {"requires": ["owner", "professional"], "min_knowledge": "detailed"},
        "steep": {"requires": ["owner", "professional", "public"], "min_knowledge": "joint"},
    },
    "checkpoints": {
        "default": ["admission", "post_verify", "approval", "release"],
        "steep_extra": ["pre_verify", "evidence"],
    },
    "switch": {
        "no_auto_resume": True,          # 不设自动恢复
        "depot_to_mainline_requires": ["owner", "professional"],  # 回正线须重新评估
    },
}


class SwitchbackGovernor:
    """Stateful governor for one or more tasks."""

    def __init__(
        self,
        ledger: Optional[KMarkerLedger] = None,
        tracer: Optional[Tracer] = None,
        policy: Optional[dict[str, Any]] = None,
        tasks_path: Optional[str] = None,
    ) -> None:
        self.policy = policy or DEFAULT_POLICY
        # 注意：不能用 `ledger or KMarkerLedger()` —— KMarkerLedger 定义了 __len__，
        # 空账本在布尔语境下为 False，会静默新建账本导致数据漂移（本项目第一课）。
        self.ledger = ledger if ledger is not None else KMarkerLedger()
        self.tracer = tracer if tracer is not None else Tracer()
        self.tasks_path = tasks_path
        self._tasks: dict[str, TaskCard] = {}
        # Tasks that have EVER reached the mainline. A task that was released and
        # then pulled into the depot must never auto-resume to the mainline.
        self._ever_mainline: set[str] = set()
        if tasks_path:
            self._load_tasks(tasks_path)

    # ------------------------------------------------------------------ #
    # 任务卡持久化（CLI 多进程复用工作区）
    # ------------------------------------------------------------------ #

    def _load_tasks(self, path: str) -> None:
        import os
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for t in data.get("tasks", []):
            card = TaskCard(
                task_id=t["task_id"], title=t["title"], grade=Grade(t["grade"]),
                owner=t["owner"], state=SwitchState(t["state"]),
                created_at=t["created_at"],
            )
            self._tasks[card.task_id] = card
        # ever_mainline 必须独立持久化：任务可能曾在正线、现已入段，
        # 仅看当前 state 会漏掉"曾被放行"的历史 → 导致自动恢复守卫失效（状态漂移）。
        self._ever_mainline = set(data.get("ever_mainline", []))
        # 兜底：兼容旧格式（无 ever_mainline 字段）时，按当前 state 推断
        if not self._ever_mainline:
            for card in self._tasks.values():
                if card.state == SwitchState.MAINLINE:
                    self._ever_mainline.add(card.task_id)

    def _save_tasks(self) -> None:
        if not self.tasks_path:
            return
        data = {
            "schema": "switchback.tasks/v1",
            "tasks": [t.to_dict() for t in self._tasks.values()],
            "ever_mainline": sorted(self._ever_mainline),
        }
        with open(self.tasks_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    # 任务准入（坡度分级）
    # ------------------------------------------------------------------ #

    def admit(self, task_id: str, title: str, grade: Grade, owner: str = "agent-manager") -> TaskCard:
        """Admission via grade-based access. All tasks start in the DEPOT state."""
        card = TaskCard(task_id=task_id, title=title, grade=grade, owner=owner)
        self._tasks[task_id] = card
        self.tracer.event(
            "task.admitted",
            {"task_id": task_id, "title": title, "grade": grade.value, "state": card.state.value},
        )
        self._save_tasks()
        return card

    def required_roles(self, grade: Grade) -> list[PartyRole]:
        spec = self.policy["admission"][grade.value]
        return [PartyRole(r) for r in spec["requires"]]

    # ------------------------------------------------------------------ #
    # 折返点
    # ------------------------------------------------------------------ #

    def open_checkpoint(
        self,
        task_id: str,
        kind: CheckpointKind,
        roles: Optional[list[PartyRole]] = None,
    ) -> Checkpoint:
        """Open a switchback node on the pipeline. The train must stop here."""
        card = self._require(task_id)
        roles = roles or self.required_roles(card.grade)
        cp = Checkpoint(kind=kind, task_id=task_id, grade=card.grade, required_roles=roles)
        self.tracer.event(
            "checkpoint.open",
            {"checkpoint_id": cp.id, "kind": kind.value, "task_id": task_id, "grade": card.grade.value},
        )
        return cp

    def vote(self, checkpoint: Checkpoint, role: PartyRole, name: str, verdict: Verdict, note: str = "") -> Verdict:
        """One party casts a vote. Any veto forces a turn-back when resolved."""
        checkpoint.add_vote(PartyVote(role=role, name=name, verdict=verdict, note=note))
        self.tracer.event(
            "checkpoint.vote",
            {
                "checkpoint_id": checkpoint.id,
                "task_id": checkpoint.task_id,
                "role": role.value,
                "verdict": verdict.value,
                "name": name,
            },
        )
        if len(checkpoint.votes) == len(checkpoint.required_roles):
            return self.resolve(checkpoint)
        return verdict

    def resolve(self, checkpoint: Checkpoint) -> Verdict:
        """All required roles must vote; any veto => TURN_BACK / DEPOT.

        Never returns an auto-resume path: a vetoed task sits in SIDING or DEPOT
        until an explicit human decision moves it.
        """
        verdict = checkpoint.resolve()
        self.tracer.event(
            "checkpoint.resolved",
            {
                "checkpoint_id": checkpoint.id,
                "task_id": checkpoint.task_id,
                "verdict": verdict.value,
            },
        )
        return verdict

    # ------------------------------------------------------------------ #
    # 道岔三态（不设自动恢复）
    # ------------------------------------------------------------------ #

    def switch(self, task_id: str, target: SwitchState, actor: str, reason: str = "") -> SwitchState:
        """Explicit switch operation. Refuses any attempt to auto-recover.

        * First admission (DEPOT -> MAINLINE, never released before) is allowed:
          it is the sanctioned path through the admission/approval gate.
        * A task that was already released and then pulled into the depot can
          only return to the mainline through ``re_enter_mainline`` (a fresh,
          human-approved checkpoint). Any other DEPOT -> MAINLINE switch is
          rejected as an unsanctioned auto-recovery.
        """
        card = self._require(task_id)
        if target == SwitchState.MAINLINE:
            if task_id in self._ever_mainline and card.state == SwitchState.DEPOT:
                if self.policy["switch"].get("no_auto_resume", True):
                    # 已被放行、后又入段的任务禁止自动恢复
                    raise NoAutoResumeError(
                        f"task {task_id} was released and is in DEPOT; re-entry to MAINLINE "
                        "requires a fresh approval checkpoint, not an automatic switch."
                    )
            self._ever_mainline.add(task_id)
        if target == SwitchState.SIDING:
            # 侧线折返 = 退回重做
            self.tracer.event("task.siding", {"task_id": task_id, "actor": actor, "reason": reason})
        elif target == SwitchState.DEPOT:
            self.tracer.event("task.depot", {"task_id": task_id, "actor": actor, "reason": reason})
        elif target == SwitchState.MAINLINE:
            self.tracer.event("task.mainline", {"task_id": task_id, "actor": actor, "reason": reason})
        card.state = target
        self._save_tasks()
        return card.state

    def turn_back(self, task_id: str, actor: str = "governor", reason: str = "veto") -> SwitchState:
        """Vetoed => forced turn-back to the siding (退回重做)."""
        return self.switch(task_id, SwitchState.SIDING, actor, reason)

    def pull_into_depot(self, task_id: str, actor: str = "governor", reason: str = "safety") -> SwitchState:
        """Safety isolation => depot maintenance."""
        return self.switch(task_id, SwitchState.DEPOT, actor, reason)

    def re_enter_mainline(self, task_id: str, actor: str, approval_checkpoint: Checkpoint) -> SwitchState:
        """Re-entry from DEPOT requires a fresh approval checkpoint that passed.

        This is the *explicit, human-approved* path back to the mainline — it is
        the only allowed way out of DEPOT and therefore bypasses the automatic
        no-auto-resume guard (which exists to block unsanctioned auto-recovery).
        """
        if approval_checkpoint.decided != Verdict.PASS:
            raise SwitchbackError("re-entry requires a PASS approval checkpoint")
        card = self._require(task_id)
        card.state = SwitchState.MAINLINE
        self._ever_mainline.add(task_id)
        self._save_tasks()
        self.tracer.event(
            "task.mainline",
            {"task_id": task_id, "actor": actor, "reason": "re-entered after fresh approval",
             "approval_checkpoint": approval_checkpoint.id},
        )
        return card.state

    # ------------------------------------------------------------------ #
    # K标版本（执行证据沉淀）
    # ------------------------------------------------------------------ #

    def seal(self, task_id: str, label: str, payload: dict[str, Any]) -> KMarker:
        """Seal a K-marker: record an immutable, content-addressed evidence entry."""
        card = self._require(task_id)
        marker = self.ledger.append(task_id=task_id, label=label, payload=payload)
        self.tracer.event(
            "ledger.sealed",
            {
                "task_id": task_id,
                "km": marker.km,
                "label": label,
                "sha256": marker.sha256,
            },
        )
        return marker

    def status(self, task_id: str) -> dict[str, Any]:
        card = self._require(task_id)
        return {"task": card.to_dict(), "last_km": self.ledger.last_km_for(task_id)}

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def _require(self, task_id: str) -> TaskCard:
        if task_id not in self._tasks:
            raise SwitchbackError(f"unknown task: {task_id}")
        return self._tasks[task_id]
