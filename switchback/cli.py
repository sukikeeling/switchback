"""Switchback CLI — the reproducible entry point.

The reviewer (or any operator) can drive the whole governance pipeline from the
terminal without touching Python:

    switchback init            # create a run workspace (policy + ledger + trace)
    switchback register <task> # admit a task (grade-access skill)
    switchback verify <task>   # run evidence-verify skill
    switchback vote <task> ... # three-party votes at the approval checkpoint
    switchback approve <task>  # resolve checkpoint => pass
    switchback reject <task>   # resolve checkpoint => turn back (veto)
    switchback seal <task>     # seal a K-marker
    switchback status <task>   # task card + switch state + last K-marker
    switchback ledger          # dump the K-marker chain
    switchback replay <case>   # replay a built-in case (jingzhang)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .governor import DEFAULT_POLICY, SwitchbackGovernor
from .ledger import KMarkerLedger, RiskLedger
from .protocol import CheckpointKind, Grade, PartyRole, SwitchState, Verdict
from .state import AgentMemory, SharedState
from .trace import Tracer

WORKSPACE_DIR = Path("switchback-run")


def _gov(ws: Path) -> SwitchbackGovernor:
    ledger_path = ws / "kmarker-ledger.json"
    trace_path = ws / "trace.jsonl"
    tasks_path = ws / "tasks.json"
    policy_path = ws / "governance.json"
    policy = DEFAULT_POLICY
    if policy_path.exists():
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    return SwitchbackGovernor(
        ledger=KMarkerLedger(str(ledger_path)),
        tracer=Tracer(str(trace_path)),
        policy=policy,
        tasks_path=str(tasks_path),
    )


def _workspace() -> Path:
    WORKSPACE_DIR.mkdir(exist_ok=True)
    return WORKSPACE_DIR


def cmd_init(args: argparse.Namespace) -> int:
    ws = _workspace()
    (ws / "governance.json").write_text(
        json.dumps(DEFAULT_POLICY, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"workspace ready: {ws.resolve()}  (policy + ledger + trace)")
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    gov = _gov(_workspace())
    grade = Grade(args.grade)
    card = gov.admit(args.task, args.title, grade, owner=args.owner)
    print(f"admitted: {card.task_id} | grade={card.grade.value} | state={card.state.value} "
          f"| required roles={[r.value for r in gov.required_roles(grade)]}")
    gov.seal(args.task, "K0 admission", {"grade": grade.value, "title": args.title})
    print("sealed: K0 admission")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from .skills import evidence_verify
    gov = _gov(_workspace())
    claims = json.loads(Path(args.claims).read_text(encoding="utf-8"))
    sources = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    report = evidence_verify(claims, sources, numeric_keys=args.numeric_keys)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if not report.passed:
        gov.turn_back(args.task, actor="verifier", reason="evidence-verify failed")
        print(f"task {args.task} -> SIDING (turned back, not auto-resumed)")
        return 1
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    gov = _gov(_workspace())
    card = gov.status(args.task)["task"]
    grade = Grade(card["grade"])
    cp = gov.open_checkpoint(args.task, CheckpointKind.APPROVAL)
    for role, name in zip([PartyRole.OWNER, PartyRole.PROFESSIONAL, PartyRole.PUBLIC],
                          ["owner", "professional", "public"]):
        gov.vote(cp, role, name, Verdict.PASS)
    verdict = cp.resolve()
    print(f"approval checkpoint {cp.id}: {verdict.value}")
    if verdict == Verdict.PASS:
        gov.switch(args.task, SwitchState.MAINLINE, actor="approver", reason="three-party approval passed")
        marker = gov.seal(args.task, f"K{args.label or 'release'}", {"verdict": "pass"})
        print(f"task {args.task} on MAINLINE | sealed {marker.to_dict()['sha256'][:16]}…")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    gov = _gov(_workspace())
    card = gov.status(args.task)["task"]
    grade = Grade(card["grade"])
    cp = gov.open_checkpoint(args.task, CheckpointKind.APPROVAL)
    gov.vote(cp, PartyRole.PUBLIC, "public", Verdict.TURN_BACK, note=args.reason or "veto")
    gov.vote(cp, PartyRole.PROFESSIONAL, "professional", Verdict.PASS)
    gov.vote(cp, PartyRole.OWNER, "owner", Verdict.PASS)
    verdict = cp.resolve()
    gov.turn_back(args.task, actor="governor", reason=args.reason or "public veto")
    print(f"approval checkpoint {cp.id}: {verdict.value} => task {args.task} -> SIDING (no auto-resume)")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    gov = _gov(_workspace())
    st = gov.status(args.task)
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    ledger = KMarkerLedger(str(_workspace() / "kmarker-ledger.json"))
    ok = ledger.verify_chain()
    print(ledger.export("md"))
    print(f"chain integrity: {'OK' if ok else 'BROKEN'}")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    if args.case == "jingzhang":
        from .cases.jingzhang import run_jingzhang_case
        run_jingzhang_case(ws=_workspace(), headless=False)
        return 0
    if args.case == "ops":
        from .cases.ops import run_ops_case
        run_ops_case(ws=_workspace(), headless=False)
        return 0
    print(f"unknown case: {args.case}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="switchback", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create run workspace")

    r = sub.add_parser("register", help="admit a task (grade-access)")
    r.add_argument("task")
    r.add_argument("--title", default="untitled task")
    r.add_argument("--grade", choices=["gentle", "medium", "steep"], default="medium")
    r.add_argument("--owner", default="agent-manager")

    v = sub.add_parser("verify", help="run evidence-verify skill")
    v.add_argument("task")
    v.add_argument("--claims", required=True)
    v.add_argument("--sources", required=True)
    v.add_argument("--numeric-keys", nargs="*", default=[])

    a = sub.add_parser("approve", help="three-party approval => pass")
    a.add_argument("task")
    a.add_argument("--label", default="release")

    j = sub.add_parser("reject", help="force turn-back (veto)")
    j.add_argument("task")
    j.add_argument("--reason")

    s = sub.add_parser("status", help="show task card")
    s.add_argument("task")

    l = sub.add_parser("ledger", help="dump K-marker chain")

    rep = sub.add_parser("replay", help="replay a built-in case")
    rep.add_argument("case", choices=["jingzhang", "ops"])

    args = p.parse_args(argv)
    return {"init": cmd_init, "register": cmd_register, "verify": cmd_verify,
            "approve": cmd_approve, "reject": cmd_reject, "status": cmd_status,
            "ledger": cmd_ledger, "replay": cmd_replay}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
