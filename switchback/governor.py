"""The Switchback Governor — a declarative rule engine over the protocol.

The Governor is the "监理 Agent" (G-GOVERNOR) of a multi-agent team. It owns:

  * **admission**      — grade-based access: steeper grades face stricter checks;
  * **checkpoints**    — the switchback nodes on the pipeline;
  * **transitions**    — the three switch states (mainline / siding / depot) with
                         **no automatic recovery** and exploration budget tracking;
  * **anti-retry**     — blocks blind "apology + reflection + retry" loops;
  * **dual-signature** — requires both G-GOVERNOR and Human Governor signatures
                         to patch parameters and re-enter mainline from DEPOT;
  * **time-machine**   — one-click rollback to any historical K-marker checkpoint;
  * **K-markers**      — every release / recalc / data update seals a ledger entry.

Governance is declared in a policy (JSON), not hard-coded, so operators can tune
review depth per grade without touching the engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Optional

from .ledger import KMarkerLedger
from .protocol import (
    AntiRetryLoopError,
    BudgetExhaustedError,
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
        "default_exploration_budget": 3, # 侧线折返默认探索预算
    },
}

_APOLOGY_PATTERNS = re.compile(
    r"(i apologize|my apologies|sorry,?\s+i\s+will\s+retry|抱歉.*重试|对不起.*再试一次|反思重试)",
    re.IGNORECASE,
)


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
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for t in data.get("tasks", []):
            card = TaskCard(
                task_id=t["task_id"],
                title=t["title"],
                grade=Grade(t["grade"]),
                owner=t["owner"],
                state=SwitchState(t["state"]),
                created_at=t["created_at"],
                exploration_budget=int(t.get("exploration_budget", 3)),
                turn_back_count=int(t.get("turn_back_count", 0)),
                retry_fingerprints=list(t.get("retry_fingerprints", [])),
                human_cosigned=bool(t.get("human_cosigned", False)),
            )
            self._tasks[card.task_id] = card
        # ever_mainline 必须独立持久化：任务可能曾在正线、现已入段，
        # 仅看当前 state 会漏掉"曾被放行"的历史 → 导致自动恢复守卫失效（状态漂移）。
        self._ever_mainline = set(data.get("ever_mainline", []))
        if not self._ever_mainline:
            for card in self._tasks.values():
                if card.state == SwitchState.MAINLINE:
                    self._ever_mainline.add(card.task_id)

    def _save_tasks(self) -> None:
        if not self.tasks_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.tasks_path)), exist_ok=True)
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

    def admit(
        self,
        task_id: str,
        title: str,
        grade: Grade,
        owner: str = "agent-manager",
        exploration_budget: Optional[int] = None,
    ) -> TaskCard:
        """Admission via grade-based access. All tasks start in the DEPOT state."""
        default_budget = int(self.policy.get("switch", {}).get("default_exploration_budget", 3))
        budget = exploration_budget if exploration_budget is not None else default_budget
        card = TaskCard(
            task_id=task_id,
            title=title,
            grade=grade,
            owner=owner,
            exploration_budget=budget,
        )
        self._tasks[task_id] = card
        self.tracer.event(
            "task.admitted",
            {
                "task_id": task_id,
                "title": title,
                "grade": grade.value,
                "state": card.state.value,
                "exploration_budget": budget,
            },
        )
        self._save_tasks()
        return card

    def required_roles(self, grade: Grade) -> list[PartyRole]:
        spec = self.policy["admission"][grade.value]
        return [PartyRole(r) for r in spec["requires"]]

    def tasks(self) -> list[TaskCard]:
        return list(self._tasks.values())

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
        """All required roles must vote; any veto => TURN_BACK / DEPOT."""
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
    # 道岔三态（不设自动恢复 + 探索预算扣减 + 拒绝无脑重试）
    # ------------------------------------------------------------------ #

    def switch(self, task_id: str, target: SwitchState, actor: str, reason: str = "") -> SwitchState:
        """Explicit switch operation. Refuses any attempt to auto-recover."""
        card = self._require(task_id)
        if target == SwitchState.MAINLINE:
            if task_id in self._ever_mainline and card.state == SwitchState.DEPOT:
                if self.policy["switch"].get("no_auto_resume", True):
                    self.tracer.event(
                        "governor.auto_resume_blocked",
                        {"task_id": task_id, "actor": actor, "reason": reason},
                    )
                    raise NoAutoResumeError(
                        f"task {task_id} was released and is in DEPOT; re-entry to MAINLINE "
                        "requires a fresh approval checkpoint, not an automatic switch."
                    )
            self._ever_mainline.add(task_id)
        if target == SwitchState.SIDING:
            self.tracer.event("task.siding", {"task_id": task_id, "actor": actor, "reason": reason})
        elif target == SwitchState.DEPOT:
            self.tracer.event("task.depot", {"task_id": task_id, "actor": actor, "reason": reason})
        elif target == SwitchState.MAINLINE:
            self.tracer.event("task.mainline", {"task_id": task_id, "actor": actor, "reason": reason})
        card.state = target
        self._save_tasks()
        return card.state

    def turn_back(
        self,
        task_id: str,
        actor: str = "governor",
        reason: str = "veto",
        enforce_budget: bool = False,
    ) -> SwitchState:
        """Vetoed => forced turn-back to the siding (退回重做) with exploration budget deduction.

        When ``enforce_budget=True`` and ``exploration_budget`` reaches 0, the task is
        automatically escalated to ``DEPOT`` (safety isolation) and raises ``BudgetExhaustedError``.
        """
        card = self._require(task_id)
        card.turn_back_count += 1
        card.exploration_budget = max(0, card.exploration_budget - 1)
        if enforce_budget and card.exploration_budget <= 0:
            self.switch(task_id, SwitchState.DEPOT, actor=actor, reason=f"exploration budget exhausted: {reason}")
            self.tracer.event(
                "task.budget_exhausted",
                {"task_id": task_id, "turn_back_count": card.turn_back_count, "reason": reason},
            )
            raise BudgetExhaustedError(
                f"task {task_id} exhausted exploration budget after {card.turn_back_count} turn-backs; locked in DEPOT."
            )
        return self.switch(task_id, SwitchState.SIDING, actor, reason)

    def pull_into_depot(self, task_id: str, actor: str = "governor", reason: str = "safety") -> SwitchState:
        """Safety isolation => depot maintenance."""
        return self.switch(task_id, SwitchState.DEPOT, actor, reason)

    def guard_retry(self, task_id: str, attempt_payload: dict[str, Any], actor: str = "worker") -> bool:
        """Anti-Retry Loop Guard (拒绝无脑道歉反思重试死循环).

        Blocks an agent from:
          1. Retrying while the task is locked in DEPOT without human intervention;
          2. Submitting a verbatim duplicate payload fingerprint after a failure;
          3. Submitting a self-apology/reflection retry without substantive parameter change.
        """
        card = self._require(task_id)
        if card.state == SwitchState.DEPOT and task_id in self._ever_mainline:
            self.tracer.event("governor.anti_retry_blocked", {"task_id": task_id, "reason": "locked_in_depot"})
            raise AntiRetryLoopError(
                f"task {task_id} is locked in DEPOT maintenance; worker {actor} cannot retry without Human Governor sign-off."
            )

        raw_text = json.dumps(attempt_payload, sort_keys=True, ensure_ascii=False)
        # Strip apology text to compute substantive parameter fingerprint
        cleaned_payload = {
            k: v for k, v in attempt_payload.items() if k not in ("apology", "reflection", "retry_note", "thought")
        }
        fp = hashlib.sha256(
            json.dumps(cleaned_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]

        has_apology = bool(_APOLOGY_PATTERNS.search(raw_text))
        if fp in card.retry_fingerprints:
            self.tracer.event(
                "governor.anti_retry_blocked",
                {"task_id": task_id, "actor": actor, "fingerprint": fp, "has_apology": has_apology},
            )
            raise AntiRetryLoopError(
                f"AntiRetryLoopError: worker {actor} attempted a duplicate/apology retry on {task_id} "
                f"(fingerprint={fp}) without human parameter patch."
            )
        if has_apology and not attempt_payload.get("human_patched"):
            self.tracer.event(
                "governor.anti_retry_blocked",
                {"task_id": task_id, "actor": actor, "reason": "apology_reflection_loop"},
            )
            raise AntiRetryLoopError(
                f"AntiRetryLoopError: self-reflection/apology retry loop detected on {task_id}; human intervention required."
            )

        card.retry_fingerprints.append(fp)
        self._save_tasks()
        return True

    def re_enter_mainline(self, task_id: str, actor: str, approval_checkpoint: Checkpoint) -> SwitchState:
        """Re-entry from DEPOT requires a fresh approval checkpoint that passed."""
        if approval_checkpoint.decided != Verdict.PASS:
            raise SwitchbackError("re-entry requires a PASS approval checkpoint")
        card = self._require(task_id)
        card.state = SwitchState.MAINLINE
        self._ever_mainline.add(task_id)
        self._save_tasks()
        self.tracer.event(
            "task.mainline",
            {
                "task_id": task_id,
                "actor": actor,
                "reason": "re-entered after fresh approval",
                "approval_checkpoint": approval_checkpoint.id,
            },
        )
        return card.state

    def human_intervene(
        self,
        task_id: str,
        human_actor: str,
        governor_actor: str,
        patched_payload: dict[str, Any],
        reason: str = "human governor cockpit intervention",
        reset_budget: int = 3,
    ) -> dict[str, Any]:
        """Dual-signature intervention (监理 Agent + 人类总指挥台双签放行).

        Patches parameters, seals a dual-signed K-marker, completes a fresh
        approval checkpoint, resets exploration budget, and returns task to MAINLINE.
        """
        if not human_actor or not governor_actor:
            raise SwitchbackError("dual signature requires both human_actor and governor_actor")
        card = self._require(task_id)
        cp = self.open_checkpoint(task_id, CheckpointKind.APPROVAL)
        for role in self.required_roles(card.grade):
            voter = human_actor if role == PartyRole.OWNER else governor_actor
            self.vote(cp, role, voter, Verdict.PASS, note=f"dual-sign: {reason}")
        if not cp.is_decided:
            self.resolve(cp)

        card.exploration_budget = reset_budget
        card.human_cosigned = True
        card.retry_fingerprints.clear()
        new_state = self.re_enter_mainline(task_id, actor=f"{human_actor}+{governor_actor}", approval_checkpoint=cp)
        marker = self.seal(
            task_id,
            "K-human-dual-sign",
            {
                "human_actor": human_actor,
                "governor_actor": governor_actor,
                "reason": reason,
                "patched_payload": patched_payload,
                "checkpoint_id": cp.id,
            },
        )
        return {
            "task_id": task_id,
            "state": new_state.value,
            "checkpoint_id": cp.id,
            "km": marker.km,
            "sha256": marker.sha256,
            "merkle_root": self.ledger.merkle_root(),
        }

    # ------------------------------------------------------------------ #
    # 一键回溯时光机（Time Machine Rollback to K-Marker）
    # ------------------------------------------------------------------ #

    def rollback_to_km(
        self,
        task_id: str,
        target_km: int,
        actor: str = "human-governor",
        reason: str = "time-machine rollback",
    ) -> dict[str, Any]:
        """Roll back a task to a verified historical K-marker checkpoint.

        Verifies the Merkle inclusion proof of `K{target_km}`, transitions the task
        to SIDING with restored snapshot payload, and appends an immutable
        `K-rollback->K{target_km}` audit entry.
        """
        card = self._require(task_id)
        target_marker = self.ledger.get_km(target_km)
        if target_marker.task_id != task_id:
            raise SwitchbackError(
                f"cannot rollback task {task_id} to K{target_km} (belongs to task {target_marker.task_id})"
            )
        proof = self.ledger.merkle_proof(target_km)
        self.ledger.verify_merkle_proof(target_km, proof)

        card.state = SwitchState.SIDING
        self._save_tasks()
        rollback_marker = self.seal(
            task_id,
            f"K-rollback-to-K{target_km}",
            {
                "rolled_back_to_km": target_km,
                "restored_sha256": target_marker.sha256,
                "restored_payload": target_marker.payload,
                "actor": actor,
                "reason": reason,
            },
        )
        self.tracer.event(
            "task.rollback",
            {
                "task_id": task_id,
                "target_km": target_km,
                "new_km": rollback_marker.km,
                "actor": actor,
                "reason": reason,
            },
        )
        return {
            "task_id": task_id,
            "state": card.state.value,
            "rolled_back_to_km": target_km,
            "restored_payload": target_marker.payload,
            "new_km": rollback_marker.km,
            "merkle_proof_verified": True,
        }

    # ------------------------------------------------------------------ #
    # K标版本（执行证据沉淀）
    # ------------------------------------------------------------------ #

    def seal(self, task_id: str, label: str, payload: dict[str, Any]) -> KMarker:
        """Seal a K-marker: record an immutable, content-addressed evidence entry."""
        self._require(task_id)
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
        return {
            "task": card.to_dict(),
            "last_km": self.ledger.last_km_for(task_id),
            "merkle_root": self.ledger.merkle_root(),
        }

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def _require(self, task_id: str) -> TaskCard:
        if task_id not in self._tasks:
            raise SwitchbackError(f"unknown task: {task_id}")
        return self._tasks[task_id]
