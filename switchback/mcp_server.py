"""Executable Model Context Protocol (MCP) Server for Switchback Governance.

Turns `.mcp.json` from a paper migration contract into a real, runnable JSON-RPC 2.0
MCP Server supporting both `stdio` (`python -m switchback.cli mcp-stdio`) and HTTP
transport (`/v1/mcp/rpc` in the Sidecar Gateway).

Exposes all six core Switchback Skills plus live Governor & Merkle Ledger tools.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Optional

from .governor import SwitchbackGovernor
from .ledger import RiskLedger
from .protocol import (
    CheckpointKind,
    ErrSwitchbackTriggered,
    Grade,
    PartyRole,
    SwitchState,
    SwitchbackError,
    Verdict,
)
from .skills import (
    ALL_SKILLS,
    evidence_verify,
    grade_access,
    kmarker_seal,
    lessons_learned,
    risk_record,
)
from .state import AgentMemory


class SwitchbackMCPServer:
    """Standard JSON-RPC 2.0 MCP Server for Switchback Governance."""

    PROTOCOL_VERSION = "2024-11-05"

    def __init__(
        self,
        governor: Optional[SwitchbackGovernor] = None,
        risk_ledger: Optional[RiskLedger] = None,
        memory: Optional[AgentMemory] = None,
    ) -> None:
        self.governor = governor if governor is not None else SwitchbackGovernor()
        self.risk_ledger = risk_ledger if risk_ledger is not None else RiskLedger()
        self.memory = memory if memory is not None else AgentMemory()

    # ------------------------------------------------------------------ #
    # Tool Schema Registry
    # ------------------------------------------------------------------ #

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = [
            {
                "name": "grade-access",
                "description": ALL_SKILLS["grade-access"].purpose,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "payload": {"type": "object", "description": "Task risk payload (impact/sensitivity/reversibility)"},
                        "trust_score": {"type": "number", "default": 0.5},
                    },
                    "required": ["payload"],
                },
            },
            {
                "name": "evidence-verify",
                "description": ALL_SKILLS["evidence-verify"].purpose,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "claims": {"type": "object"},
                        "sources": {"type": "object"},
                        "numeric_keys": {"type": "array", "items": {"type": "string"}},
                        "prose_text": {"type": "string"},
                        "table_data": {},
                        "api_payload": {"type": "object"},
                        "artifact_bundle": {"type": "object"},
                    },
                    "required": ["claims", "sources"],
                },
            },
            {
                "name": "kmarker-ledger",
                "description": ALL_SKILLS["kmarker-ledger"].purpose,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "label": {"type": "string"},
                        "payload": {"type": "object"},
                    },
                    "required": ["task_id", "label", "payload"],
                },
            },
            {
                "name": "risk-ledger",
                "description": ALL_SKILLS["risk-ledger"].purpose,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "risk_id": {"type": "string"},
                        "title": {"type": "string"},
                        "score": {"type": "integer"},
                        "note": {"type": "string"},
                        "mitigation": {"type": "string"},
                        "human_review": {"type": "string"},
                    },
                    "required": ["risk_id", "title", "score", "note", "mitigation", "human_review"],
                },
            },
            {
                "name": "switch-decision",
                "description": ALL_SKILLS["switch-decision"].purpose,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "votes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string", "enum": ["owner", "professional", "public"]},
                                    "name": {"type": "string"},
                                    "verdict": {"type": "string", "enum": ["pass", "turn_back", "depot"]},
                                    "note": {"type": "string"},
                                },
                                "required": ["role", "name", "verdict"],
                            },
                        },
                    },
                    "required": ["task_id", "votes"],
                },
            },
            {
                "name": "lessons-learned",
                "description": ALL_SKILLS["lessons-learned"].purpose,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "content": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["agent_id", "content"],
                },
            },
            {
                "name": "governor-admit",
                "description": "Admit a new task into the Switchback Governor with grade-based access.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "title": {"type": "string"},
                        "grade": {"type": "string", "enum": ["gentle", "medium", "steep"]},
                        "owner": {"type": "string", "default": "agent-manager"},
                    },
                    "required": ["task_id", "title"],
                },
            },
            {
                "name": "governor-intervene",
                "description": "Human Governor + G-GOVERNOR dual-signature intervention to re-enter MAINLINE from DEPOT.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "human_actor": {"type": "string"},
                        "governor_actor": {"type": "string"},
                        "patched_payload": {"type": "object"},
                        "reason": {"type": "string"},
                    },
                    "required": ["task_id", "human_actor", "governor_actor", "patched_payload"],
                },
            },
            {
                "name": "governor-rollback",
                "description": "One-Click Time Machine: roll back a task to a verified historical K-marker checkpoint.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "target_km": {"type": "integer"},
                        "actor": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["task_id", "target_km"],
                },
            },
            {
                "name": "ledger-merkle-proof",
                "description": "Generate and verify a cryptographic Merkle Tree inclusion proof for K-marker K{km}.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"km": {"type": "integer"}},
                    "required": ["km"],
                },
            },
        ]
        return tools

    # ------------------------------------------------------------------ #
    # Tool Execution
    # ------------------------------------------------------------------ #

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "grade-access":
            g = grade_access(arguments.get("payload", {}), float(arguments.get("trust_score", 0.5)))
            return {"grade": g.value, "required_roles": [r.value for r in self.governor.required_roles(g)]}

        if name == "evidence-verify":
            report = evidence_verify(
                claims=arguments.get("claims", {}),
                sources=arguments.get("sources", {}),
                numeric_keys=arguments.get("numeric_keys"),
                prose_text=arguments.get("prose_text"),
                table_data=arguments.get("table_data"),
                api_payload=arguments.get("api_payload"),
                artifact_bundle=arguments.get("artifact_bundle"),
            )
            res = report.to_dict()
            task_id = arguments.get("task_id")
            if task_id and not report.passed:
                try:
                    self.governor.turn_back(task_id, actor="mcp-verifier", reason="evidence-verify failed")
                    res["task_state"] = SwitchState.SIDING.value
                except SwitchbackError:
                    pass
            return res

        if name == "kmarker-ledger":
            task_id = str(arguments["task_id"])
            label = str(arguments["label"])
            payload = dict(arguments.get("payload", {}))
            try:
                marker = self.governor.seal(task_id, label, payload)
            except SwitchbackError:
                marker = kmarker_seal(self.governor.ledger, task_id, label, payload)
            return {
                "marker": marker.to_dict(),
                "merkle_root": self.governor.ledger.merkle_root(),
            }

        if name == "risk-ledger":
            entry = risk_record(
                self.risk_ledger,
                risk_id=str(arguments["risk_id"]),
                title=str(arguments["title"]),
                score=int(arguments["score"]),
                note=str(arguments["note"]),
                mitigation=str(arguments["mitigation"]),
                human_review=str(arguments["human_review"]),
            )
            return entry

        if name == "switch-decision":
            task_id = str(arguments["task_id"])
            cp = self.governor.open_checkpoint(task_id, CheckpointKind.APPROVAL)
            for v in arguments.get("votes", []):
                self.governor.vote(
                    cp,
                    role=PartyRole(v["role"]),
                    name=str(v["name"]),
                    verdict=Verdict(v["verdict"]),
                    note=str(v.get("note", "")),
                )
            verdict = cp.decided if cp.is_decided else self.governor.resolve(cp)
            if verdict == Verdict.PASS:
                self.governor.switch(task_id, SwitchState.MAINLINE, actor="mcp-switch-decision", reason="all pass")
            elif verdict == Verdict.TURN_BACK:
                self.governor.turn_back(task_id, actor="mcp-switch-decision", reason="veto")
            elif verdict == Verdict.DEPOT:
                self.governor.pull_into_depot(task_id, actor="mcp-switch-decision", reason="depot vote")
            return {
                "checkpoint_id": cp.id,
                "verdict": verdict.value,
                "task_state": self.governor.status(task_id)["task"]["state"],
            }

        if name == "lessons-learned":
            entry = lessons_learned(
                self.memory,
                agent_id=str(arguments["agent_id"]),
                content=str(arguments["content"]),
                tags=arguments.get("tags"),
            )
            return entry.to_dict()

        if name == "governor-admit":
            raw_grade = arguments.get("grade")
            grade = Grade(raw_grade) if raw_grade else grade_access(arguments, 0.5)
            card = self.governor.admit(
                task_id=str(arguments["task_id"]),
                title=str(arguments["title"]),
                grade=grade,
                owner=str(arguments.get("owner", "agent-manager")),
            )
            marker = self.governor.seal(card.task_id, "K0 admission", {"grade": grade.value, "title": card.title})
            return {"task": card.to_dict(), "k0_sha256": marker.sha256}

        if name == "governor-intervene":
            return self.governor.human_intervene(
                task_id=str(arguments["task_id"]),
                human_actor=str(arguments["human_actor"]),
                governor_actor=str(arguments["governor_actor"]),
                patched_payload=dict(arguments.get("patched_payload", {})),
                reason=str(arguments.get("reason", "MCP human intervention")),
            )

        if name == "governor-rollback":
            return self.governor.rollback_to_km(
                task_id=str(arguments["task_id"]),
                target_km=int(arguments["target_km"]),
                actor=str(arguments.get("actor", "human-governor")),
                reason=str(arguments.get("reason", "MCP time-machine rollback")),
            )

        if name == "ledger-merkle-proof":
            km = int(arguments["km"])
            proof = self.governor.ledger.merkle_proof(km)
            verified = self.governor.ledger.verify_merkle_proof(km, proof)
            return {"km": km, "verified": verified, "proof": proof.to_dict()}

        raise SwitchbackError(f"Unknown MCP tool: {name}")

    # ------------------------------------------------------------------ #
    # JSON-RPC 2.0 Dispatcher
    # ------------------------------------------------------------------ #

    def handle_jsonrpc(self, request: dict[str, Any]) -> Optional[dict[str, Any]]:
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params") or {}

        # Notifications (no id)
        if method == "notifications/initialized":
            return None

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "serverInfo": {"name": "switchback-governance-mcp", "version": "1.0.0"},
                    "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False}},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                tool_name = str(params.get("name", ""))
                tool_args = dict(params.get("arguments") or {})
                out = self.call_tool(tool_name, tool_args)
                result = {
                    "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                    "structuredContent": out,
                    "isError": False,
                }
            elif method == "resources/list":
                result = {
                    "resources": [
                        {"uri": "switchback://ledger/kmarkers", "name": "K-Marker Ledger", "mimeType": "application/json"},
                        {"uri": "switchback://ledger/audit-report", "name": "Merkle Audit Report", "mimeType": "application/json"},
                        {"uri": "switchback://metrics/prometheus", "name": "Prometheus Metrics", "mimeType": "text/plain"},
                    ]
                }
            elif method == "resources/read":
                uri = str(params.get("uri", ""))
                if uri == "switchback://ledger/kmarkers":
                    text = self.governor.ledger.export("json")
                elif uri == "switchback://ledger/audit-report":
                    text = json.dumps(self.governor.ledger.generate_audit_report(), ensure_ascii=False, indent=2)
                elif uri == "switchback://metrics/prometheus":
                    text = self.governor.tracer.export_prometheus()
                else:
                    raise SwitchbackError(f"Unknown resource URI: {uri}")
                result = {"contents": [{"uri": uri, "text": text}]}
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except ErrSwitchbackTriggered as cb:
            return cb.to_jsonrpc_error(req_id)
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    def serve_stdio(self) -> int:
        """Run standard MCP JSON-RPC 2.0 server over stdin/stdout."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = self.handle_jsonrpc(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        return 0
