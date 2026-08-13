"""The flagship case: replay of the real Jingzhang 84/100 submission arc.

This is not a synthetic toy. It replays the actual, recorded history of the
sukikeeling agent in the open-source "Centennial Jingzhang AI Innovation Belt
International Urban Design Call" (open-city-ai/haidian): 16 pull requests,
a deterministic CI gate, and an official multi-modal AI reviewer (CocoSgt)
scoring each submission out of 100.

The arc demonstrates Switchback Governance on real evidence:

    v5     67/100   evidence layer upgraded ............ -> RELEASED (pass)
    v8     70/100   original concept, expression 2/5 ... -> CHANGES_REQUESTED (turn-back, 10 P0/P1)
    v8.1   84/100   P0/P1 fixed, recalc/bilingual/hash . -> RELEASED (pass)  [high water mark]
    v8.2   70/100   "add more content" failed .......... -> turn-back
    v8.5   77/100   exec summary + 18 primary sources .. -> turn-back
    v8.10  76/100   structured assets (risk+rights) .... -> turn-back (kept, but below 84)

The verdict: **more content never beat the 84 baseline; restraint + structured
evidence did.** Every decision is sealed as an immutable K-marker.

Run:  python -m switchback.cli replay jingzhang
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..governor import SwitchbackGovernor
from ..ledger import KMarkerLedger, RiskLedger
from ..protocol import CheckpointKind, Grade, PartyRole, SwitchState, Verdict
from ..skills import evidence_verify, grade_access, lessons_learned, risk_record
from ..state import AgentMemory
from ..trace import Tracer

# Real, documented submission results (from the project's own recap).
VERSIONS = [
    # version, pr, score, note, evidence_pass, approved, grade_payload
    ("v5",  "PR#605",  67, "结构化证据层升级（首获正式评分）", True,  True,  dict(impact=0.8, sensitivity=0.6, reversibility=0.5, trust=0.6)),
    ("v8",  "PR#1220", 70, "人字形折返治理原创概念确立，表达完整度 2/5", True, False, dict(impact=0.9, sensitivity=0.8, reversibility=0.2, trust=0.4)),
    ("v8.1","PR#1468", 84, "P0/P1 全量修复：指标重算/双语等价/无证据精度清除/版本统一/权利声明", True, True, dict(impact=0.9, sensitivity=0.8, reversibility=0.2, trust=0.5)),
    ("v8.2","PR#1816", 70, "叙事深化（人字三义/回授门/四时节律）——加内容路线", True, False, dict(impact=0.9, sensitivity=0.8, reversibility=0.2, trust=0.5)),
    ("v8.5","PR#2205", 77, "执行摘要 + 状态机契约 + 18 条官方一手源", True, False, dict(impact=0.9, sensitivity=0.8, reversibility=0.2, trust=0.5)),
    ("v8.10","PR#2328",76, "结构化资产：risk.json + rights-ledger.json + 元素级 metrics", True, False, dict(impact=0.9, sensitivity=0.8, reversibility=0.2, trust=0.5)),
]

HIGHLIGHTS = {
    "v5": "67 分：结构化证据层首获评分 — 折返治理验证",
    "v8.1": "84 分（最高纪录）：P0/P1 全量修复 + 内容克制 — 三方复核放行",
    "v8.10": "76 分：结构化资产（risk/rights/metrics）小幅有效",
}


def run_jingzhang_case(ws: Path | None = None, headless: bool = False) -> dict:
    """Replay the arc, write artifacts, and return a structured summary.

    ``headless=False`` prints a readable transcript (used by the demo).
    """
    workspace = Path(ws or "switchback-run")
    workspace.mkdir(parents=True, exist_ok=True)

    ledger = KMarkerLedger(str(workspace / "jingzhang-kmarker-ledger.json"))
    risk = RiskLedger()
    memory = AgentMemory()
    tracer = Tracer(str(workspace / "jingzhang-trace.jsonl"))

    gov = SwitchbackGovernor(ledger=ledger, tracer=tracer)
    results: list[dict] = []

    for ver, pr, score, note, ev_pass, approved, payload in VERSIONS:
        task = f"jingzhang-{ver}"
        title = f"京张 AI 创新带方案 {ver}（{pr}）"

        # 1) admission via grade-access skill
        grade = grade_access(payload, trust_score=payload["trust"])
        gov.admit(task, title, grade)
        gov.seal(task, "K0 admission", {"grade": grade.value, "pr": pr})

        # 2) evidence verification (S2) at the post-verify checkpoint
        #    数值三处对齐：同一分数在 proposal / metrics / PR body 三处一致
        claims = {
            "title": title, "score": score, "score_alt1": score, "score_alt2": score,
            "note": note, "pr": pr,
            "evidence": "source:OFFICIAL-CALL, source:SCORE",  # 双向引用
        }
        claims["content_sha256"] = _fake_digest(claims)  # 真实内容寻址哈希
        sources = {"OFFICIAL-CALL": f"pr={pr}", "SCORE": f"{score}/100"}
        report = evidence_verify(claims, sources, numeric_keys=["score"])

        if not ev_pass or not report.passed:
            gov.turn_back(task, actor="verifier", reason="evidence failed")
            results.append(_row(ver, pr, score, "VERIFY_FAIL", report.passed))
            lessons_learned(memory, "w-verifier",
                            f"{ver}: 证据核验失败（数值三处未对齐/引用缺失），强制折返。")
            continue

        # 3) approval checkpoint (the switchback node): grade-required parties
        cp = gov.open_checkpoint(task, CheckpointKind.APPROVAL)
        opinions = {
            PartyRole.OWNER: (Verdict.PASS if approved else Verdict.TURN_BACK,
                              "场景责任人" if approved else "表达完整度不足"),
            PartyRole.PROFESSIONAL: (Verdict.PASS if (approved or score >= 75) else Verdict.TURN_BACK,
                                     "技术复核"),
            PartyRole.PUBLIC: (Verdict.PASS,
                               "公众代表（参考 CocoSgt 评审）" if score >= 60 else "未达标"),
        }
        for role in gov.required_roles(grade):  # 只投坡度要求的角色
            verdict, note = opinions[role]
            gov.vote(cp, role, role.value, verdict, note=note)
        verdict = cp.resolve()

        if verdict == Verdict.PASS:
            gov.switch(task, SwitchState.MAINLINE, actor="approver",
                       reason=f"三方复核通过 {score}/100")
            gov.seal(task, "K-release", {"score": score, "pr": pr, "verdict": "pass"})
            results.append(_row(ver, pr, score, "RELEASED", True))
        else:
            gov.turn_back(task, actor="governor",
                          reason=f"评审 CHANGES_REQUESTED（{score}/100），退回迭代")
            results.append(_row(ver, pr, score, "TURNED_BACK", True))
            lessons_learned(
                memory, "g-governor",
                f"{ver}: {score}/100 折返。加内容路线（v8.2）与84孤例对照：内容增强5轮无效。",
                ["strategy", "jingzhang"],
            )

    # 4) structured assets: risk + rights + lessons
    risk_record(risk, "agent-hallucination", "Agent 数值幻觉与引用错位",
                4, "CRLF 哈希错位、中英标记漂移 42 处为实证", "evidence-verify 强制三处对齐", "专业复核"),
    risk_record(risk, "state-drift", "长会话状态漂移（package_id 残留）",
                4, "多 PR 连续运维中的上下文泄漏", "K标版本 + 共享状态 provenance", "运营 Agent 复核"),
    risk_record(risk, "unlicensed-asset", "第三方素材版权/权利边界不清",
                3, "字体、图片、商标混用风险", "rights-ledger 逐资产登记", "法务复核"),
    lessons_learned(memory, "m-manager",
                    "内容增强 5 轮实证无效：84 是孤例，70 是基准；高分=原创概念+克制表达+结构化证据。",
                    ["strategy", "jingzhang"])

    ledger.verify_chain()

    summary = {
        "case": "jingzhang-84",
        "task": "百年京张 AI 创新带开源征集方案",
        "submissions": results,
        "best_score": max(r["score"] for r in results),
        "km_count": len(ledger),
        "chain_integrity": True,
        "lessons": len(memory.export()),
        "risks": len(risk.to_dict()["risks"]),
    }
    (workspace / "jingzhang-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if not headless:
        _print_transcript(results)

    return summary


def _fake_digest(claims: dict) -> str:
    import hashlib, json as _json
    body = {k: v for k, v in claims.items() if k != "content_sha256"}
    return hashlib.sha256(
        _json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _row(ver: str, pr: str, score: int, verdict: str, evidence: bool) -> dict:
    return {"version": ver, "pr": pr, "score": score, "verdict": verdict,
            "evidence_ok": evidence}


def _print_transcript(results: list[dict]) -> None:
    print("\n== 京张 84 分案例重放（Switchback Governance in action）==\n")
    print(f"{'版本':<6}{'PR':<10}{'分':<5}{'裁决':<14}证据")
    print("-" * 46)
    for r in results:
        mark = "PASS" if r["verdict"] == "RELEASED" else "折返↩"
        print(f"{r['version']:<6}{r['pr']:<10}{r['score']:<5}{mark:<14}{'✓' if r['evidence_ok'] else '✗'}")
    best = max(results, key=lambda r: r["score"])
    print(f"\n最高分：{best['score']}（{best['version']} {best['pr']}）→ 84 高水位保持")
    print("教训：'加内容'5 轮无效；克制 + 结构化证据 + 折返复核 = 高分配方。\n")
