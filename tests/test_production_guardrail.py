"""Tests for the Industrial Production Guardrail (v1.0):
  1. Merkle Tree & SQLite WAL Atomic K-Marker Ledger
  2. Live Evidence Engine (3-way live numeric, citation snapshot lock, atomic package CRLF/package_id/bilingual drift)
  3. Strict State Machine (Exploration Budget -> DEPOT, Anti-Retry Apology Guard, Dual-Sign Release, Time Machine Rollback)
  4. Live Sidecar HTTP/JSON-RPC/MCP Gateway & Physical Hard Circuit Breaker (ErrSwitchbackTriggered)
  5. OTLP/JSON Trace Exporter, W3C TraceContext & Prometheus /metrics
  6. AgentTeams Matrix Room Bus, M5 Benchmark Suite & M6 DevSecOps Case
"""

from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from switchback import (
    AGENTTEAMS_ROSTER,
    AgentTeamsCluster,
    AntiRetryLoopError,
    BudgetExhaustedError,
    ErrSwitchbackTriggered,
    Grade,
    KMarkerLedger,
    LedgerIntegrityError,
    LiveEvidenceEngine,
    MatrixRoomBus,
    MerkleTree,
    PartyRole,
    SidecarHTTPServer,
    SwitchState,
    SwitchbackGovernor,
    SwitchbackMCPServer,
    SwitchbackSidecarGateway,
    Tracer,
    Verdict,
    format_im_card,
)
from switchback.benchmark import run_benchmark_suite
from switchback.cases.devsecops import run_devsecops_case


# --------------------------------------------------------------------------- #
# 1. Merkle Tree & SQLite WAL 持久化与并发安全测试
# --------------------------------------------------------------------------- #

def test_merkle_tree_proofs_across_odd_and_even_sizes():
    for count in (1, 2, 3, 4, 7, 11):
        leaves = [f"leaf-{i:04d}" for i in range(count)]
        tree = MerkleTree(leaves)
        assert tree.size == count
        assert len(tree.root) == 64
        for idx in range(count):
            proof = tree.get_proof(idx)
            assert MerkleTree.verify_proof(proof, expected_root=tree.root) is True
            # Tamper with leaf hash -> verification must fail
            bad_proof = tree.get_proof(idx)
            bad_proof.leaf_hash = "tampered"
            assert MerkleTree.verify_proof(bad_proof, expected_root=tree.root) is False


def test_sqlite_wal_atomic_ledger_and_concurrent_appends():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "kmarkers.db")
        json_path = str(Path(tmp) / "kmarkers.json")
        ledger = KMarkerLedger(path=json_path, sqlite_path=db_path)

        def worker(tid: int):
            for step in range(5):
                ledger.append(f"task-{tid}", f"K-step-{step}", {"tid": tid, "step": step})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(ledger) == 20
        assert ledger.verify_chain() is True
        root1 = ledger.merkle_root()
        assert len(root1) == 64

        # Reload from SQLite WAL database in a fresh instance
        reloaded = KMarkerLedger(sqlite_path=db_path)
        assert len(reloaded) == 20
        assert reloaded.verify_chain() is True
        assert reloaded.merkle_root() == root1

        # Verify Merkle proof & legal audit report
        proof = reloaded.merkle_proof(13)
        assert reloaded.verify_merkle_proof(13, proof) is True
        audit = reloaded.generate_audit_report()
        assert audit["chain_integrity"] is True
        assert audit["merkle_root"] == root1
        assert audit["entries_count"] == 20
        assert len(audit["report_sha256"]) == 64


# --------------------------------------------------------------------------- #
# 2. Live Evidence Engine（活体证据核验器：三处数值 + 引用快照 + 原子包防漂移）
# --------------------------------------------------------------------------- #

def test_live_three_way_numeric_extraction_and_mismatch():
    prose = "本次压测核心指标 score: 84，吞吐量 qps = 12500.5，详见附件表格。"
    table = "| 指标 | 数值 |\n|---|---|\n| score | 84 |\n| qps | 12500.5 |"
    api_ok = {"data": {"score": 84, "qps": 12500.5}}
    checks_ok = LiveEvidenceEngine.verify_three_way_live(prose, table, api_ok, ["score", "qps"])
    assert all(c["ok"] for c in checks_ok)

    # API returns 70 while prose & table claim 84 -> must fail
    api_bad = {"data": {"score": 70, "qps": 12500.5}}
    checks_bad = LiveEvidenceEngine.verify_three_way_live(prose, table, api_bad, ["score", "qps"])
    score_check = next(c for c in checks_bad if c["key"] == "score")
    assert score_check["ok"] is False
    assert score_check["sources"] == {"prose": 84.0, "table": 84.0, "api": 70.0}


def test_live_source_snapshot_404_and_hash_tamper():
    snap_ok = LiveEvidenceEngine.probe_source("S1", {"uri": "inline:s1", "content": "official fact"})
    assert snap_ok.ok is True

    snap_404 = LiveEvidenceEngine.probe_source("S2", {"uri": "https://example.invalid/404", "simulate_404": True})
    assert snap_404.ok is False
    assert snap_404.status == "HTTP_404"

    snap_tampered = LiveEvidenceEngine.probe_source(
        "S3",
        {"uri": "inline:s3", "content": "modified content", "expected_sha256": snap_ok.sha256},
    )
    assert snap_tampered.ok is False
    assert snap_tampered.to_dict()["status"] == "HASH_DRIFT"


def test_atomic_package_crlf_package_id_and_bilingual_drift():
    # Clean package
    clean_res = LiveEvidenceEngine.verify_atomic_package(
        {
            "zh.md": "package_id: pkg-v10\nversion: v10\n[ANCHOR:SEC-1] 折返治理\n",
            "en.md": "package_id: pkg-v10\nversion: v10\n[ANCHOR:SEC-1] Switchback Governance\n",
        },
        expected_package_id="pkg-v10",
        expected_version="v10",
        bilingual_pair=("zh.md", "en.md"),
    )
    assert clean_res["passed"] is True

    # Drifted package: CRLF in zh.md + stale package_id in en.md + missing anchor + CJK residue in en.md
    dirty_res = LiveEvidenceEngine.verify_atomic_package(
        {
            "zh.md": "package_id: pkg-v10\r\nversion: v10\r\n[ANCHOR:SEC-1] [ANCHOR:SEC-2] 折返治理\r\n",
            "en.md": "package_id: pkg-v8\nversion: v8\n[ANCHOR:SEC-1] Switchback 残留中文\n",
        },
        expected_package_id="pkg-v10",
        expected_version="v10",
        bilingual_pair=("zh.md", "en.md"),
    )
    assert dirty_res["passed"] is False
    by_name = {c["check"]: c for c in dirty_res["checks"]}
    assert by_name["crlf_hash_alignment"]["ok"] is False
    assert by_name["package_id_consistency"]["ok"] is False
    assert by_name["bilingual_marker_alignment"]["ok"] is False
    assert by_name["bilingual_marker_alignment"]["cjk_residue_in_en_count"] >= 1


# --------------------------------------------------------------------------- #
# 3. 探索预算耗尽入段、防无脑重试、人类双签放行与一键时光机回溯
# --------------------------------------------------------------------------- #

def test_exploration_budget_exhaustion_escalates_to_depot():
    gov = SwitchbackGovernor()
    gov.admit("b-task", "budget test", Grade.MEDIUM, exploration_budget=2)
    gov.switch("b-task", SwitchState.MAINLINE, actor="approver", reason="initial")
    # 1st turn-back: budget 2 -> 1 (stays in SIDING)
    assert gov.turn_back("b-task", enforce_budget=True) == SwitchState.SIDING
    assert gov.status("b-task")["task"]["exploration_budget"] == 1
    # 2nd turn-back: budget 1 -> 0 (escalates to DEPOT & raises BudgetExhaustedError)
    with pytest.raises(BudgetExhaustedError):
        gov.turn_back("b-task", enforce_budget=True)
    assert gov.status("b-task")["task"]["state"] == SwitchState.DEPOT.value


def test_anti_retry_loop_guard_blocks_apology_and_duplicates():
    gov = SwitchbackGovernor()
    gov.admit("r-task", "retry test", Grade.GENTLE)
    # 1st substantive attempt is allowed
    assert gov.guard_retry("r-task", {"param": 42}) is True
    # Duplicate payload with apology is blocked
    with pytest.raises(AntiRetryLoopError):
        gov.guard_retry("r-task", {"param": 42, "apology": "I apologize, I will retry"})
    # Pure apology loop on new payload without human_patched is also blocked
    with pytest.raises(AntiRetryLoopError):
        gov.guard_retry("r-task", {"param": 43, "note": "对不起，我再试一次"})


def test_human_dual_sign_intervene_and_time_machine_rollback():
    gov = SwitchbackGovernor()
    gov.admit("tm-task", "time machine test", Grade.STEEP)
    k0 = gov.seal("tm-task", "K0 baseline", {"config": "safe-v1"})
    gov.switch("tm-task", SwitchState.MAINLINE, actor="approver", reason="initial")
    gov.seal("tm-task", "K1 bad-mutation", {"config": "corrupted-v2"})
    gov.pull_into_depot("tm-task", actor="sidecar", reason="incident")

    # Dual-signature intervention brings task back to MAINLINE
    res = gov.human_intervene(
        task_id="tm-task",
        human_actor="sukikeeling",
        governor_actor="G-GOVERNOR",
        patched_payload={"config": "patched-v3"},
        reason="cockpit manual fix",
    )
    assert res["state"] == SwitchState.MAINLINE.value
    assert gov.status("tm-task")["task"]["human_cosigned"] is True

    # Time Machine rollback to K0 restores K0 payload and verifies Merkle proof
    rb = gov.rollback_to_km("tm-task", target_km=k0.km, actor="sukikeeling")
    assert rb["rolled_back_to_km"] == 0
    assert rb["restored_payload"] == {"config": "safe-v1"}
    assert rb["merkle_proof_verified"] is True
    assert gov.status("tm-task")["task"]["state"] == SwitchState.SIDING.value


# --------------------------------------------------------------------------- #
# 4. Sidecar 网关 HTTP / JSON-RPC / MCP / Prometheus / OTLP 全链路真机测试
# --------------------------------------------------------------------------- #

def test_sidecar_http_server_mcp_prometheus_otlp_and_cockpit():
    gov = SwitchbackGovernor()
    gw = SwitchbackSidecarGateway(governor=gov)
    srv = SidecarHTTPServer(gateway=gw, host="127.0.0.1", port=0)
    base_url = srv.start_background()
    try:
        # 1) Benign intercept -> HTTP 200 + MAINLINE
        req_pass = urllib.request.Request(
            f"{base_url}/v1/govern/intercept",
            data=json.dumps({
                "task_id": "http-t1",
                "actor": "W-VERIFY",
                "tool": "doc.check",
                "consumer_token": "ctok_w_verify",
                "payload": {"impact": 0.3},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_pass, timeout=5) as resp:
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
            assert body["ok"] is True
            assert body["state"] == "mainline"
            assert resp.headers.get("traceparent", "").startswith("00-")

        # 2) Destructive SQL + Secret leak -> HTTP 423 Locked + ErrSwitchbackTriggered + DEPOT
        req_fail = urllib.request.Request(
            f"{base_url}/v1/govern/intercept",
            data=json.dumps({
                "task_id": "http-t1",
                "actor": "W-CREATE",
                "tool": "db.migrate",
                "payload": {"sql": "DROP TABLE users;", "key": "sk-abcdefghijklmnopqrstuvwxyz123456"},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req_fail, timeout=5)
        assert exc_info.value.code == 423
        err_body = json.loads(exc_info.value.read().decode("utf-8"))
        assert err_body["error"] == "ErrSwitchbackTriggered"
        assert err_body["target_state"] == "depot"

        # 3) Subsequent request while in DEPOT is physically blocked (No Auto-Resume!)
        with pytest.raises(urllib.error.HTTPError) as exc_depot:
            urllib.request.urlopen(req_pass, timeout=5)
        assert exc_depot.value.code == 423

        # 4) Cockpit Dual-Sign Intervention via HTTP `/api/intervene` unlocks DEPOT -> MAINLINE
        req_intervene = urllib.request.Request(
            f"{base_url}/api/intervene",
            data=json.dumps({
                "task_id": "http-t1",
                "human_actor": "sukikeeling",
                "governor_actor": "G-GOVERNOR",
                "patched_payload": {"sql": "SELECT 1;"},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_intervene, timeout=5) as resp:
            iv_body = json.loads(resp.read().decode("utf-8"))
            assert iv_body["ok"] is True
            assert iv_body["state"] == "mainline"

        # 5) MCP JSON-RPC 2.0 endpoint `/v1/mcp/rpc`
        mcp_req = urllib.request.Request(
            f"{base_url}/v1/mcp/rpc",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(mcp_req, timeout=5) as resp:
            mcp_body = json.loads(resp.read().decode("utf-8"))
            tool_names = {t["name"] for t in mcp_body["result"]["tools"]}
            assert {"grade-access", "evidence-verify", "kmarker-ledger", "switch-decision"}.issubset(tool_names)

        # 6) Prometheus `/metrics`, OTLP `/v1/traces/otlp`, Audit `/v1/audit/report`, Cockpit `/`
        with urllib.request.urlopen(f"{base_url}/metrics", timeout=5) as resp:
            prom_text = resp.read().decode("utf-8")
            assert "switchback_circuit_breaks_total" in prom_text
            assert "switchback_state_transitions_total" in prom_text

        with urllib.request.urlopen(f"{base_url}/v1/traces/otlp", timeout=5) as resp:
            otlp_data = json.loads(resp.read().decode("utf-8"))
            assert "resourceSpans" in otlp_data
            assert len(otlp_data["resourceSpans"][0]["scopeSpans"][0]["spans"]) >= 1

        with urllib.request.urlopen(f"{base_url}/v1/audit/report", timeout=5) as resp:
            audit_data = json.loads(resp.read().decode("utf-8"))
            assert audit_data["chain_integrity"] is True
            assert len(audit_data["merkle_root"]) == 64

        with urllib.request.urlopen(f"{base_url}/", timeout=5) as resp:
            html = resp.read().decode("utf-8")
            assert "Human Governor WebUI Cockpit" in html
    finally:
        srv.stop()


# --------------------------------------------------------------------------- #
# 5. AgentTeams Matrix 集群、M5 评测基准与 M6 第三案例端到端测试
# --------------------------------------------------------------------------- #

def test_agentteams_roster_and_im_card():
    assert set(AGENTTEAMS_ROSTER.keys()) == {"M-OPER", "W-RESEARCH", "W-CREATE", "W-VERIFY", "W-RISK", "G-GOVERNOR"}
    card = format_im_card("t-1", "credential_leak", "depot", "a" * 64)
    assert card["body"]["auto_resume"].startswith("DISABLED")
    assert len(card["actions"]) == 3


def test_devsecops_third_case_and_benchmark_suite():
    with tempfile.TemporaryDirectory() as tmp:
        dev_summary = run_devsecops_case(ws=Path(tmp), headless=True)
        assert dev_summary["chain_integrity"] is True
        assert dev_summary["retry_loop_blocked"] is True
        assert len(dev_summary["merkle_root"]) == 64
        stage_verdicts = {s["stage"]: s["verdict"] for s in dev_summary["stages"]}
        assert stage_verdicts["db-migration-v1"] == "CIRCUIT_BROKEN"
        assert stage_verdicts["cockpit-dual-sign"] == "DUAL_SIGNED_MAINLINE"
        assert stage_verdicts["benchmark-verify-v1"] == "CIRCUIT_BROKEN"
        assert stage_verdicts["canary-release-v2"] == "RELEASED"

        bench = run_benchmark_suite(ws=Path(tmp), headless=True)
        assert bench["interception_recall"] == 1.0
        assert bench["interception_precision"] == 1.0
        assert bench["false_positives"] == 0
        assert bench["false_negatives"] == 0
        assert bench["chain_integrity"] is True


def test_mcp_server_all_tools_and_resources():
    mcp = SwitchbackMCPServer()
    assert mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 0, "method": "initialize"})["result"]["protocolVersion"] == "2024-11-05"
    assert mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "ping"})["result"] == {}

    # 1. governor-admit
    r_admit = mcp.call_tool("governor-admit", {"task_id": "mcp-t1", "title": "MCP Task", "grade": "steep"})
    assert r_admit["task"]["grade"] == "steep"

    # 2. grade-access
    r_grade = mcp.call_tool("grade-access", {"payload": {"impact": 0.9, "sensitivity": 0.9, "reversibility": 0.1}, "trust_score": 0.2})
    assert r_grade["grade"] == "steep"

    # 3. evidence-verify
    r_ev = mcp.call_tool("evidence-verify", {
        "task_id": "mcp-t1",
        "claims": {"score": 84, "score_alt1": 84, "score_alt2": 84, "cite": "source:S1"},
        "sources": {"S1": "doc"},
        "numeric_keys": ["score"],
    })
    assert r_ev["passed"] is True

    # 4. kmarker-ledger & ledger-merkle-proof
    r_km = mcp.call_tool("kmarker-ledger", {"task_id": "mcp-t1", "label": "K-step", "payload": {"ok": True}})
    assert len(r_km["merkle_root"]) == 64
    r_proof = mcp.call_tool("ledger-merkle-proof", {"km": r_km["marker"]["km"]})
    assert r_proof["verified"] is True

    # 5. risk-ledger & lessons-learned
    r_risk = mcp.call_tool("risk-ledger", {
        "risk_id": "R1", "title": "Drift", "score": 4, "note": "n", "mitigation": "m", "human_review": "h"
    })
    assert r_risk["flag"] == "mandatory_human_review"
    r_les = mcp.call_tool("lessons-learned", {"agent_id": "W-VERIFY", "content": "lesson 1", "tags": ["mcp"]})
    assert r_les["agent_id"] == "W-VERIFY"

    # 6. switch-decision (depot vote -> DEPOT) then governor-intervene -> MAINLINE then governor-rollback
    r_sd = mcp.call_tool("switch-decision", {
        "task_id": "mcp-t1",
        "votes": [
            {"role": "owner", "name": "O", "verdict": "depot"},
            {"role": "professional", "name": "P", "verdict": "pass"},
            {"role": "public", "name": "U", "verdict": "pass"},
        ],
    })
    assert r_sd["verdict"] == "depot"
    r_iv = mcp.call_tool("governor-intervene", {
        "task_id": "mcp-t1",
        "human_actor": "sukikeeling",
        "governor_actor": "G-GOVERNOR",
        "patched_payload": {"fixed": 1},
    })
    assert r_iv["state"] == "mainline"
    r_rb = mcp.call_tool("governor-rollback", {"task_id": "mcp-t1", "target_km": 0})
    assert r_rb["rolled_back_to_km"] == 0

    # 7. resources/list & resources/read
    res_list = mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})
    assert len(res_list["result"]["resources"]) == 3
    for uri in ("switchback://ledger/kmarkers", "switchback://ledger/audit-report", "switchback://metrics/prometheus"):
        read_resp = mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {"uri": uri}})
        assert len(read_resp["result"]["contents"][0]["text"]) > 10


def test_cli_new_subcommands_end_to_end(tmp_path, monkeypatch):
    from switchback.cli import main
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert main(["register", "cli-t1", "--title", "CLI Test", "--grade", "medium"]) == 0
    assert main(["approve", "cli-t1"]) == 0
    assert main(["reject", "cli-t1", "--reason", "recheck"]) == 0
    assert main(["intervene", "cli-t1", "--human", "sukikeeling", "--governor", "G-GOVERNOR", "--patch", '{"a":1}']) == 0
    assert main(["rollback", "cli-t1", "--km", "0"]) == 0
    assert main(["audit", "--task", "cli-t1"]) == 0
    assert main(["replay", "devsecops"]) == 0
    assert main(["benchmark"]) == 0

