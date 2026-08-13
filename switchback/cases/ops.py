"""The second independent case: zero-touch ops (告警聚合→根因→修复→恢复→复盘).

GOAI Track-1 reference direction #1: zero human ops. This case proves the
Switchback Governance protocol is industry-portable — the same four mechanisms
that governed the Jingzhang urban-design submission arc now govern a production
incident on a stateless web service.

Arc (one incident, four sub-tasks, each its own switchback node):

    1. alert-triage      告警聚合    grade=medium   -> root cause proposed
    2. root-cause         根因定位    grade=steep    -> 三方复核（修复方案前必停）
       ↳ fix proposal     修复执行    grade=steep    -> owner 否决：回滚有风险 → 侧线折返
       ↳ fix v2           修复执行 v2  grade=steep    -> 三方通过 → 放行
    3. recovery-verify    恢复验证    grade=medium   -> evidence-verify 通过 → 放行
    4. postmortem         事故复盘    grade=gentle   -> lessons-learned 写回

The interesting bit: the FIRST fix proposal is vetoed at the switchback node
(the owner flags a risky rollback), forcing a turn-back to the siding; the
SECOND, safer fix passes the same three-party review. No auto-resume — the
incident stays in the siding until a human-approved fix clears the checkpoint.

Run:  python -m switchback.cli replay ops
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..governor import SwitchbackGovernor
from ..ledger import KMarkerLedger, RiskLedger
from ..protocol import CheckpointKind, Grade, PartyRole, SwitchState, Verdict
from ..skills import evidence_verify, grade_access, lessons_learned, risk_record
from ..state import AgentMemory
from ..trace import Tracer

# One production incident, modeled as four sub-tasks.
# Each tuple: (task_id, title, grade_payload, approved, veto_role_or_None)
STAGES = [
    # (1) 告警聚合：多源告警收敛到单一事故，定级。根因由 Agent 提出但须经复核。
    ("alert-triage", "事故 INC-2026-0813：支付服务 5xx 飙升",
     dict(impact=0.7, sensitivity=0.5, reversibility=0.8, trust=0.7),
     True, None),
    # (2) 根因定位 + 修复方案：陡坡。第一次方案被责任人否决（回滚风险），折返侧线。
    ("fix-v1", "修复方案 v1：全量回滚至上一版本",
     dict(impact=0.9, sensitivity=0.9, reversibility=0.1, trust=0.5),
     False, PartyRole.OWNER),  # 责任人否决：回滚会丢数据
    # (2b) 修复方案 v2：金丝雀 + 热补丁，三方通过。
    ("fix-v2", "修复方案 v2：金丝雀灰度 + 热补丁（不回滚）",
     dict(impact=0.9, sensitivity=0.7, reversibility=0.6, trust=0.5),
     True, None),
    # (3) 恢复验证：error rate 归零的证据核验。
    ("recovery-verify", "恢复验证：5xx 恢复至基线、无新告警",
     dict(impact=0.7, sensitivity=0.4, reversibility=0.8, trust=0.7),
     True, None),
    # (4) 事故复盘：缓坡，经验沉淀。
    ("postmortem", "事故复盘：根因/时间线/改进项写回知识库",
     dict(impact=0.4, sensitivity=0.2, reversibility=1.0, trust=0.9),
     True, None),
]


def run_ops_case(ws: Path | None = None, headless: bool = False) -> dict:
    """Replay a zero-touch-ops incident under Switchback Governance."""
    workspace = Path(ws or "switchback-run")
    workspace.mkdir(parents=True, exist_ok=True)

    ledger = KMarkerLedger(str(workspace / "ops-kmarker-ledger.json"))
    risk = RiskLedger()
    memory = AgentMemory()
    tracer = Tracer(str(workspace / "ops-trace.jsonl"))
    gov = SwitchbackGovernor(ledger=ledger, tracer=tracer)
    results: list[dict] = []

    for task, title, payload, approved, veto_role in STAGES:
        # 1) 坡度分级准入
        grade = grade_access(payload, trust_score=payload["trust"])
        gov.admit(task, title, grade)
        gov.seal(task, "K0 admission", {"grade": grade.value, "stage": task})

        # 2) 证据核验（恢复验证阶段做严格三处对齐；其余阶段做基础核验）
        if task == "recovery-verify":
            claims = {
                "error_rate": 0.0, "error_rate_alt1": 0.0, "error_rate_alt2": 0.0,
                "new_alerts": 0, "evidence": "source:PROMETHEUS, source:ALERTMANAGER",
            }
        else:
            claims = {"title": title, "stage": task,
                      "evidence": "source:INC-2026-0813"}
        claims["content_sha256"] = _digest(claims)
        sources = ({"PROMETHEUS": "rate=http_5xx=0", "ALERTMANAGER": "active=0"}
                   if task == "recovery-verify" else {"INC-2026-0813": "incident record"})
        numeric = ["error_rate"] if task == "recovery-verify" else []
        report = evidence_verify(claims, sources, numeric_keys=numeric)
        if not report.passed:
            gov.turn_back(task, actor="verifier", reason="recovery evidence failed")
            results.append(_row(task, "VERIFY_FAIL", grade.value, False))
            continue

        # 3) 折返点三方复核
        cp = gov.open_checkpoint(task, CheckpointKind.APPROVAL)
        for role in gov.required_roles(grade):
            if veto_role == role and not approved:
                verdict, note = Verdict.TURN_BACK, _veto_note(task)
            else:
                verdict, note = Verdict.PASS, f"{role.value} 通过"
            gov.vote(cp, role, role.value, verdict, note=note)
        verdict = cp.resolve()

        if verdict == Verdict.PASS:
            gov.switch(task, SwitchState.MAINLINE, actor="approver",
                       reason=f"{grade.value} 三方复核通过")
            gov.seal(task, "K-release", {"stage": task, "verdict": "pass"})
            results.append(_row(task, "RELEASED", grade.value, True))
        else:
            gov.turn_back(task, actor="governor", reason=_veto_note(task))
            results.append(_row(task, "TURNED_BACK", grade.value, True))
            lessons_learned(memory, "w-verify",
                            f"{task}: 折返。{_veto_note(task)}",
                            ["ops", "incident"])

    # 结构化风险台账（事故专属风险）
    risk_record(risk, "risky-rollback", "回滚导致数据丢失风险",
                4, "fix-v1 全量回滚会丢未落库支付", "责任人否决，强制侧线折返", "值班 SRE"),
    risk_record(risk, "alert-fatigue", "告警疲劳导致根因误判",
                3, "多源告警未收敛", "alert-triage 阶段收敛 + 坡度分级", "SRE 团队"),
    risk_record(risk, "incomplete-recovery", "恢复验证不充分",
                3, "5xx 下降但未归零即放行", "recovery-verify 强制三处对齐", "监控复核"),
    lessons_learned(memory, "m-manager",
                    "运维事故同样适用折返治理：陡坡（影响大/难回滚）必须三方复核，"
                    "责任人一票即可否决有风险的修复——与京张评审如出一辙。",
                    ["ops", "strategy", "cross-industry"])

    ledger.verify_chain()
    summary = {
        "case": "ops-zero-touch",
        "task": "生产事故 INC-2026-0813 自主闭环",
        "stages": results,
        "released": sum(1 for r in results if r["verdict"] == "RELEASED"),
        "turned_back": sum(1 for r in results if r["verdict"] == "TURNED_BACK"),
        "km_count": len(ledger),
        "chain_integrity": True,
        "lessons": len(memory.export()),
        "risks": len(risk.to_dict()["risks"]),
    }
    (workspace / "ops-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if not headless:
        _print_transcript(results)
    return summary


def _digest(claims: dict) -> str:
    body = {k: v for k, v in claims.items() if k != "content_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _veto_note(task: str) -> str:
    return "全量回滚会丢失未落库支付数据，责任人否决，退回侧线重做（不自动恢复）"


def _row(task: str, verdict: str, grade: str, evidence: bool) -> dict:
    return {"stage": task, "verdict": verdict, "grade": grade, "evidence_ok": evidence}


def _print_transcript(results: list[dict]) -> None:
    print("\n== 运维事故自主闭环（Switchback Governance · 跨行业复用）==")
    print("  事故 INC-2026-0813：支付服务 5xx 飙升\n")
    print(f"{'阶段':<18}{'裁决':<14}{'坡度':<8}证据")
    print("-" * 46)
    for r in results:
        mark = "PASS" if r["verdict"] == "RELEASED" else "折返↩"
        print(f"{r['stage']:<18}{mark:<14}{r['grade']:<8}{'✓' if r['evidence_ok'] else '✗'}")
    tb = sum(1 for r in results if r["verdict"] == "TURNED_BACK")
    print(f"\n关键：fix-v1 因回滚风险被责任人一票否决→侧线折返；fix-v2 金丝雀方案三方通过放行。")
    print(f"折返 {tb} 次，放行 {len(results)-tb} 次，全程不设自动恢复。")
    print("跨行业复用实证：同一套折返治理协议，从城市设计评审到生产事故运维。\n")
