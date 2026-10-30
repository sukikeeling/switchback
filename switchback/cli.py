"""Switchback CLI — the reproducible entry point for governance, Sidecar, MCP & Cockpit.

Drive the entire production governance pipeline from the terminal:

    switchback init                 # create a run workspace (policy + ledger + trace)
    switchback register <task>      # admit a task (grade-access skill)
    switchback verify <task>        # run Live Evidence Engine (evidence-verify skill)
    switchback vote <task> ...      # three-party votes at the approval checkpoint
    switchback approve <task>       # resolve checkpoint => pass
    switchback reject <task>        # resolve checkpoint => turn back (veto)
    switchback intervene <task> ... # Human Governor + G-GOVERNOR dual-sign release
    switchback rollback <task> ...  # One-click Time Machine rollback to K-marker
    switchback seal <task>          # seal a K-marker
    switchback status <task>        # task card + switch state + last K-marker + Merkle Root
    switchback ledger               # dump the K-marker chain & Merkle Root
    switchback audit                # generate legal Merkle audit report
    switchback replay <case>        # replay a built-in case (jingzhang / ops / devsecops)
    switchback benchmark            # run M5 guardrail benchmark & Skill Portal export
    switchback mcp-stdio            # run standard MCP JSON-RPC 2.0 server over stdio
    switchback serve                # start Live Sidecar Gateway & Human Governor WebUI
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .governor import DEFAULT_POLICY, SwitchbackGovernor
from .ledger import KMarkerLedger, RiskLedger
from .protocol import CheckpointKind, Grade, PartyRole, SwitchState, Verdict
from .state import AgentMemory, SharedState
from .trace import Tracer

WORKSPACE_DIR = Path("switchback-run")


def _ensure_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if type(stream).__name__ == "TextIOWrapper" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _gov(ws: Path) -> SwitchbackGovernor:
    ledger_path = ws / "kmarker-ledger.json"
    sqlite_path = ws / "kmarker-ledger.db"
    trace_path = ws / "trace.jsonl"
    tasks_path = ws / "tasks.json"
    policy_path = ws / "governance.json"
    policy = DEFAULT_POLICY
    if policy_path.exists():
        try:
            loaded = json.loads(policy_path.read_text(encoding="utf-8"))
            if loaded and "admission" in loaded:
                policy = loaded
        except Exception:
            pass
    return SwitchbackGovernor(
        ledger=KMarkerLedger(str(ledger_path), sqlite_path=str(sqlite_path)),
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
    print(f"workspace ready: {ws.resolve()}  (policy + ledger + sqlite-wal + trace)")
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
    # 先校验 task 已注册，再跑证据核验——避免"先打 JSON 后抛 unknown task"的顺序 bug
    try:
        gov.status(args.task)
    except Exception:
        print(f"error: unknown task '{args.task}' — run `register {args.task}` first", file=sys.stderr)
        return 2
    claims = json.loads(Path(args.claims).read_text(encoding="utf-8"))
    sources = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    report = evidence_verify(claims, sources, numeric_keys=args.numeric_keys)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if not report.passed:
        gov.turn_back(args.task, actor="verifier", reason="evidence-verify failed")
        print(f"task {args.task} -> SIDING (turned back, not auto-resumed)")
        return 1
    return 0


def cmd_vote(args: argparse.Namespace) -> int:
    """Cast a single party vote on the current approval checkpoint."""
    gov = _gov(_workspace())
    gov.status(args.task)
    cp = gov.open_checkpoint(args.task, CheckpointKind.APPROVAL)
    role = PartyRole(args.role)
    verdict = Verdict(args.verdict)
    gov.vote(cp, role, args.name, verdict, note=args.note or "")
    if len(cp.votes) == len(cp.required_roles):
        v = cp.decided if cp.is_decided else cp.resolve()
        print(f"checkpoint {cp.id}: {v.value}")
        if v == Verdict.TURN_BACK:
            gov.turn_back(args.task, actor="governor", reason=f"{role.value} veto")
            print(f"task {args.task} -> SIDING (no auto-resume)")
        elif v == Verdict.DEPOT:
            gov.pull_into_depot(args.task, actor="governor", reason=f"{role.value} depot")
            print(f"task {args.task} -> DEPOT (no auto-resume)")
    else:
        print(f"vote recorded ({len(cp.votes)}/{len(cp.required_roles)}); awaiting more votes")
    return 0


def cmd_seal(args: argparse.Namespace) -> int:
    """Seal a K-marker into the immutable ledger."""
    gov = _gov(_workspace())
    gov.status(args.task)
    payload = json.loads(args.payload) if args.payload else {}
    marker = gov.seal(args.task, args.label, payload)
    print(f"sealed: K{marker.km} {args.label} | sha256={marker.sha256[:16]}… | merkle={gov.ledger.merkle_root()[:16]}…")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    gov = _gov(_workspace())
    card = gov.status(args.task)["task"]
    grade = Grade(card["grade"])
    cp = gov.open_checkpoint(args.task, CheckpointKind.APPROVAL)
    for role in gov.required_roles(grade):
        gov.vote(cp, role, role.value, Verdict.PASS)
    verdict = cp.decided if cp.is_decided else cp.resolve()
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
    req_roles = gov.required_roles(grade)
    for idx, role in enumerate(req_roles):
        v = Verdict.TURN_BACK if idx == 0 else Verdict.PASS
        gov.vote(cp, role, role.value, v, note=args.reason or "veto")
    verdict = cp.decided if cp.is_decided else cp.resolve()
    gov.turn_back(args.task, actor="governor", reason=args.reason or "public veto")
    print(f"approval checkpoint {cp.id}: {verdict.value} => task {args.task} -> SIDING (no auto-resume)")
    return 0


def cmd_intervene(args: argparse.Namespace) -> int:
    gov = _gov(_workspace())
    patched = json.loads(args.patch) if args.patch else {}
    res = gov.human_intervene(
        task_id=args.task,
        human_actor=args.human,
        governor_actor=args.governor,
        patched_payload=patched,
        reason=args.reason,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    gov = _gov(_workspace())
    res = gov.rollback_to_km(
        task_id=args.task,
        target_km=args.km,
        actor=args.actor,
        reason=args.reason,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    gov = _gov(_workspace())
    st = gov.status(args.task)
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    ws = _workspace()
    ledger = KMarkerLedger(str(ws / "kmarker-ledger.json"), sqlite_path=str(ws / "kmarker-ledger.db"))
    ok = ledger.verify_chain()
    print(ledger.export("md"))
    print(f"chain integrity: {'OK' if ok else 'BROKEN'} | merkle_root: {ledger.merkle_root()[:16]}…")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    ws = _workspace()
    ledger = KMarkerLedger(str(ws / "kmarker-ledger.json"), sqlite_path=str(ws / "kmarker-ledger.db"))
    report = ledger.generate_audit_report(task_id=args.task)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    if args.case == "jingzhang":
        from .cases.jingzhang import run_jingzhang_case, verify_live
        if getattr(args, "live", False):
            report = verify_live()
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        run_jingzhang_case(ws=_workspace(), headless=False)
        return 0
    if args.case == "ops":
        from .cases.ops import run_ops_case
        run_ops_case(ws=_workspace(), headless=False)
        return 0
    if args.case == "devsecops":
        from .cases.devsecops import run_devsecops_case
        run_devsecops_case(ws=_workspace(), headless=False)
        return 0
    print(f"unknown case: {args.case}", file=sys.stderr)
    return 2


def cmd_benchmark(args: argparse.Namespace) -> int:
    from .benchmark import run_benchmark_suite
    run_benchmark_suite(ws=_workspace(), headless=False)
    return 0


def cmd_mcp_stdio(args: argparse.Namespace) -> int:
    from .mcp_server import SwitchbackMCPServer
    srv = SwitchbackMCPServer(governor=_gov(_workspace()))
    return srv.serve_stdio()


def cmd_serve(args: argparse.Namespace) -> int:
    from .sidecar import SidecarHTTPServer, SwitchbackSidecarGateway
    gw = SwitchbackSidecarGateway(governor=_gov(_workspace()))
    srv = SidecarHTTPServer(gateway=gw, host=args.host, port=args.port)
    url = srv.start_background()
    print(f"Switchback Live Sidecar & Human Governor Cockpit listening on {url}")
    if args.once:
        srv.stop()
        return 0
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        srv.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_console()
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

    vote = sub.add_parser("vote", help="cast a single party vote at approval checkpoint")
    vote.add_argument("task")
    vote.add_argument("--role", choices=["owner", "professional", "public"], required=True)
    vote.add_argument("--name", required=True)
    vote.add_argument("--verdict", choices=["pass", "turn_back", "depot"], required=True)
    vote.add_argument("--note", default="")

    iv = sub.add_parser("intervene", help="Human Governor + G-GOVERNOR dual-sign release from DEPOT")
    iv.add_argument("task")
    iv.add_argument("--human", default="human-governor")
    iv.add_argument("--governor", default="G-GOVERNOR")
    iv.add_argument("--patch", default="{}")
    iv.add_argument("--reason", default="human cockpit dual-sign release")

    rb = sub.add_parser("rollback", help="Time Machine rollback to a verified K-marker")
    rb.add_argument("task")
    rb.add_argument("--km", type=int, required=True)
    rb.add_argument("--actor", default="human-governor")
    rb.add_argument("--reason", default="time-machine rollback")

    seal = sub.add_parser("seal", help="seal a K-marker into the ledger")
    seal.add_argument("task")
    seal.add_argument("--label", default="release")
    seal.add_argument("--payload", default=None, help="JSON string payload")

    s = sub.add_parser("status", help="show task card")
    s.add_argument("task")

    sub.add_parser("ledger", help="dump K-marker chain & Merkle Root")

    aud = sub.add_parser("audit", help="generate Merkle-verified machine behavior audit report")
    aud.add_argument("--task", default=None)

    rep = sub.add_parser("replay", help="replay a built-in case")
    rep.add_argument("case", choices=["jingzhang", "ops", "devsecops"])
    rep.add_argument("--live", action="store_true",
                     help="jingzhang: verify PRs exist via GitHub API (real, not scripted)")

    sub.add_parser("benchmark", help="run M5 guardrail benchmark & export Skill Portal manifest")
    sub.add_parser("mcp-stdio", help="run standard MCP JSON-RPC 2.0 server over stdin/stdout")

    srv = sub.add_parser("serve", help="start Live Sidecar Gateway & Human Governor WebUI")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8780)
    srv.add_argument("--once", action="store_true", help="start and immediately stop (for self-test)")

    args = p.parse_args(argv)
    return {
        "init": cmd_init,
        "register": cmd_register,
        "verify": cmd_verify,
        "vote": cmd_vote,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "intervene": cmd_intervene,
        "rollback": cmd_rollback,
        "seal": cmd_seal,
        "status": cmd_status,
        "ledger": cmd_ledger,
        "audit": cmd_audit,
        "replay": cmd_replay,
        "benchmark": cmd_benchmark,
        "mcp-stdio": cmd_mcp_stdio,
        "serve": cmd_serve,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
