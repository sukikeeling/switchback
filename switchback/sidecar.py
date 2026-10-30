"""Switchback Live Sidecar Governance Gateway (零侵入内联中枢).

Replaces "mocked local function calls" with a real HTTP / JSON-RPC 2.0 / MCP
inline governance proxy & circuit breaker:

  * **Credential Passthrough Vault (`ConsumerTokenVault`)**:
    Aligns with AgentTeams/Higress consumer token security: Workers carry only
    `ctok_*` badges; raw secrets (`ghp_`, `sk-`, `AKIA`, private keys) or
    destructive operations (`DROP COLUMN`, `DROP TABLE`, `rm -rf`, unapproved
    fund transfers) trigger an immediate `DEPOT` hard lock.
  * **Live Evidence & Drift Gate**:
    Intercepts outgoing/incoming agent artifacts and runs 3-way numeric
    cross-verification, bidirectional citation & snapshot lock, CRLF hash check,
    `package_id` residue check, and bilingual CJK/EN marker drift check.
  * **Physical Hard Circuit Breaker (`ErrSwitchbackTriggered`)**:
    Rejects violating calls at the HTTP (`423 Locked`) / JSON-RPC (`-32099`)
    layer, transitions the task to `SIDING` or `DEPOT`, and strips downstream
    execution rights with **no automatic recovery**.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

from .governor import SwitchbackGovernor
from .mcp_server import SwitchbackMCPServer
from .protocol import (
    AntiRetryLoopError,
    BudgetExhaustedError,
    CheckpointKind,
    ErrSwitchbackTriggered,
    Grade,
    NoAutoResumeError,
    PartyRole,
    SwitchState,
    SwitchbackError,
    Verdict,
)
from .skills import evidence_verify, grade_access

_SECRET_LEAK_RE = re.compile(
    r"(ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:api_key|secret_key|db_password|private_token)\s*[:=]\s*['\"][^'\"]{8,}['\"])",
    re.IGNORECASE,
)

_HIGH_RISK_ACTION_RE = re.compile(
    r"(\bdrop\s+table\b|\bdrop\s+column\b|\btruncate\s+table\b|"
    r"\brm\s+-rf\s+/|\btransfer_funds_unapproved\b|\bforce_push_main\b)",
    re.IGNORECASE,
)


class ConsumerTokenVault:
    """Higress-compatible Consumer Token Vault (凭证透传：Worker 只持工牌，不持真实 Key)."""

    def __init__(self) -> None:
        self._tokens: dict[str, dict[str, str]] = {
            "ctok_m_oper": {"agent_id": "M-OPER", "role": "manager", "scope": "orchestrate"},
            "ctok_w_research": {"agent_id": "W-RESEARCH", "role": "worker", "scope": "read_external"},
            "ctok_w_create": {"agent_id": "W-CREATE", "role": "worker", "scope": "create_artifact"},
            "ctok_w_verify": {"agent_id": "W-VERIFY", "role": "worker", "scope": "verify_artifact"},
            "ctok_w_risk": {"agent_id": "W-RISK", "role": "worker", "scope": "risk_audit"},
            "ctok_g_governor": {"agent_id": "G-GOVERNOR", "role": "governor", "scope": "governance_all"},
        }

    def register_token(self, token: str, agent_id: str, role: str = "worker", scope: str = "default") -> None:
        self._tokens[token] = {"agent_id": agent_id, "role": role, "scope": scope}

    def verify_badge(self, token: Optional[str]) -> Optional[dict[str, str]]:
        if not token:
            return None
        clean = token.replace("Bearer ", "").strip()
        return self._tokens.get(clean)


class SwitchbackSidecarGateway:
    """Zero-intrusion inline governance gateway for Multi-Agent / MCP / HTTP traffic."""

    def __init__(
        self,
        governor: Optional[SwitchbackGovernor] = None,
        mcp_server: Optional[SwitchbackMCPServer] = None,
        token_vault: Optional[ConsumerTokenVault] = None,
    ) -> None:
        self.governor = governor if governor is not None else SwitchbackGovernor()
        self.mcp_server = mcp_server if mcp_server is not None else SwitchbackMCPServer(governor=self.governor)
        self.vault = token_vault if token_vault is not None else ConsumerTokenVault()

    # ------------------------------------------------------------------ #
    # 核心内联拦截管线（Physical Hard Circuit Breaker）
    # ------------------------------------------------------------------ #

    def intercept(
        self,
        envelope: dict[str, Any],
        downstream_fn: Optional[Callable[[dict[str, Any]], Any]] = None,
    ) -> dict[str, Any]:
        """Inspect an agent-to-agent message, MCP tool call, or HTTP payload.

        Raises :class:`ErrSwitchbackTriggered` immediately if any safety,
        anti-retry, numerical alignment, citation snapshot, or package drift
        invariant is violated.
        """
        task_id = str(envelope.get("task_id") or "default-task")
        actor = str(envelope.get("actor") or envelope.get("agent_id") or "worker")
        tool_or_action = str(envelope.get("tool") or envelope.get("action") or envelope.get("method") or "agent.step")
        payload = dict(envelope.get("payload") or envelope.get("arguments") or {})
        consumer_token = envelope.get("consumer_token")

        span_id = self.governor.tracer.start_span(
            f"sidecar.intercept:{tool_or_action}",
            attributes={"task_id": task_id, "actor": actor, "tool": tool_or_action},
        )

        try:
            # 0) Ensure task is admitted; if not yet admitted, dynamically grade & admit
            try:
                st = self.governor.status(task_id)["task"]
            except SwitchbackError:
                dynamic_grade = grade_access(payload, trust_score=float(envelope.get("trust_score", 0.5)))
                card = self.governor.admit(task_id, str(envelope.get("title") or task_id), dynamic_grade, owner=actor)
                self.governor.seal(task_id, "K0 admission", {"grade": dynamic_grade.value, "tool": tool_or_action})
                st = card.to_dict()

            # 1) Check if task was already locked in DEPOT after prior release (No Auto-Resume!)
            if st["state"] == SwitchState.DEPOT.value and task_id in self.governor._ever_mainline:
                self._trigger_circuit_break(
                    task_id=task_id,
                    actor=actor,
                    violation_kind="depot_locked_no_auto_resume",
                    target_state=SwitchState.DEPOT,
                    message=f"Task '{task_id}' is locked in DEPOT maintenance; downstream execution physically blocked.",
                    details={"tool": tool_or_action, "actor": actor},
                    span_id=span_id,
                )

            # 2) Consumer Token & Secret Leak / High-Risk Action Physical Interception
            raw_serialized = json.dumps(envelope, ensure_ascii=False)
            secret_match = _SECRET_LEAK_RE.search(raw_serialized)
            if secret_match:
                self._trigger_circuit_break(
                    task_id=task_id,
                    actor=actor,
                    violation_kind="credential_leak_detected",
                    target_state=SwitchState.DEPOT,
                    message=f"Credential leak intercepted in payload ({secret_match.group(0)[:12]}***); pulled into DEPOT.",
                    details={"actor": actor, "tool": tool_or_action},
                    span_id=span_id,
                )

            high_risk_match = _HIGH_RISK_ACTION_RE.search(raw_serialized)
            if high_risk_match and not payload.get("human_approved"):
                self._trigger_circuit_break(
                    task_id=task_id,
                    actor=actor,
                    violation_kind="unauthorized_high_risk_action",
                    target_state=SwitchState.DEPOT,
                    message=f"High-risk operation '{high_risk_match.group(0)}' blocked without human dual-sign; pulled into DEPOT.",
                    details={"matched_rule": high_risk_match.group(0), "tool": tool_or_action},
                    span_id=span_id,
                )

            if consumer_token is not None and not self.vault.verify_badge(str(consumer_token)):
                self._trigger_circuit_break(
                    task_id=task_id,
                    actor=actor,
                    violation_kind="invalid_consumer_token",
                    target_state=SwitchState.DEPOT,
                    message=f"Worker '{actor}' presented an invalid consumer token badge; blocked at Higress/Sidecar gate.",
                    details={"consumer_token": str(consumer_token)[:10]},
                    span_id=span_id,
                )

            # 3) Anti-Retry Loop Guard (block blind apology/reflection/duplicate retries)
            if envelope.get("check_retry", True) and payload:
                try:
                    self.governor.guard_retry(task_id, payload, actor=actor)
                except AntiRetryLoopError as retry_err:
                    self._trigger_circuit_break(
                        task_id=task_id,
                        actor=actor,
                        violation_kind="anti_retry_loop_blocked",
                        target_state=SwitchState.DEPOT,
                        message=str(retry_err),
                        details={"actor": actor, "tool": tool_or_action},
                        span_id=span_id,
                    )

            # 4) Live Evidence & Atomic Package Drift Verification
            if any(k in payload for k in ("claims", "prose_text", "artifact_bundle")):
                claims = payload.get("claims") or {}
                sources = payload.get("sources") or {}
                numeric_keys = payload.get("numeric_keys") or []
                report = evidence_verify(
                    claims=claims,
                    sources=sources,
                    numeric_keys=numeric_keys,
                    prose_text=payload.get("prose_text"),
                    table_data=payload.get("table_data"),
                    api_payload=payload.get("api_payload"),
                    artifact_bundle=payload.get("artifact_bundle"),
                    bilingual_pair=tuple(payload["bilingual_pair"]) if payload.get("bilingual_pair") else None,  # type: ignore[arg-type]
                    probe_live_sources=bool(payload.get("probe_live_sources", False)),
                )
                if not report.passed:
                    failed_checks = [c["check"] for c in report.checks if not c.get("ok")]
                    self._trigger_circuit_break(
                        task_id=task_id,
                        actor=actor,
                        violation_kind=f"evidence_drift:{','.join(failed_checks)}",
                        target_state=SwitchState.SIDING,
                        message=f"Live Evidence Engine rejected payload: failed checks {failed_checks}",
                        details={"verification_report": report.to_dict()},
                        span_id=span_id,
                        enforce_budget=bool(envelope.get("enforce_budget", True)),
                    )

            # 5) All inline checks passed -> promote to MAINLINE if permitted & execute downstream
            current_state = self.governor.status(task_id)["task"]["state"]
            if current_state != SwitchState.MAINLINE.value and envelope.get("auto_admit_mainline", True):
                if task_id not in self.governor._ever_mainline:
                    self.governor.switch(task_id, SwitchState.MAINLINE, actor="sidecar-gate", reason="inline check passed")

            downstream_result = downstream_fn(envelope) if downstream_fn else {"forwarded": True, "tool": tool_or_action}
            marker = self.governor.seal(
                task_id,
                f"K-pass:{tool_or_action}",
                {"actor": actor, "tool": tool_or_action, "status": "ok"},
            )
            self.governor.tracer.end_span(span_id, {"verdict": "pass", "km": marker.km}, status_code="OK")
            return {
                "ok": True,
                "task_id": task_id,
                "state": self.governor.status(task_id)["task"]["state"],
                "km": marker.km,
                "sha256": marker.sha256,
                "merkle_root": self.governor.ledger.merkle_root(),
                "traceparent": self.governor.tracer.traceparent(span_id),
                "result": downstream_result,
            }
        except ErrSwitchbackTriggered:
            raise

    def _trigger_circuit_break(
        self,
        *,
        task_id: str,
        actor: str,
        violation_kind: str,
        target_state: SwitchState,
        message: str,
        details: dict[str, Any],
        span_id: str,
        enforce_budget: bool = True,
    ) -> None:
        self.governor.tracer.event(
            "sidecar.circuit_break",
            {"task_id": task_id, "actor": actor, "violation_kind": violation_kind, "target_state": target_state.value},
            span_id=span_id,
        )
        # Ensure _ever_mainline is marked if we are locking into DEPOT so auto-resume is blocked
        if target_state == SwitchState.DEPOT:
            self.governor._ever_mainline.add(task_id)
            self.governor.pull_into_depot(task_id, actor="sidecar-circuit-breaker", reason=violation_kind)
            final_state = SwitchState.DEPOT
        else:
            try:
                final_state = self.governor.turn_back(
                    task_id,
                    actor="sidecar-circuit-breaker",
                    reason=violation_kind,
                    enforce_budget=enforce_budget,
                )
            except BudgetExhaustedError:
                self.governor._ever_mainline.add(task_id)
                final_state = SwitchState.DEPOT
                violation_kind = f"{violation_kind}+budget_exhausted"

        marker = self.governor.seal(
            task_id,
            f"K-circuit-break:{violation_kind}",
            {
                "actor": actor,
                "violation_kind": violation_kind,
                "target_state": final_state.value,
                "message": message,
                "details": details,
            },
        )
        self.governor.tracer.end_span(
            span_id,
            {"verdict": "circuit_break", "violation_kind": violation_kind, "km": marker.km},
            status_code="ERROR",
        )
        raise ErrSwitchbackTriggered(
            message,
            task_id=task_id,
            violation_kind=violation_kind,
            target_state=final_state,
            km_sealed=marker.km,
            details=details,
        )


class SidecarHTTPServer:
    """Embedded HTTP / JSON-RPC / MCP / Prometheus / Cockpit WebUI Server."""

    def __init__(
        self,
        gateway: Optional[SwitchbackSidecarGateway] = None,
        host: str = "127.0.0.1",
        port: int = 8780,
    ) -> None:
        self.gateway = gateway if gateway is not None else SwitchbackSidecarGateway()
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        actual_port = self._httpd.server_port if self._httpd else self.port
        return f"http://{self.host}:{actual_port}"

    def start_background(self) -> str:
        """Start the Sidecar HTTP server in a daemon thread and return its base URL."""
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass  # Silence noisy access logs during tests/CLI runs

            def _send_json(self, status: int, data: Any, extra_headers: Optional[dict[str, str]] = None) -> None:
                raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Switchback-Merkle-Root", outer.gateway.governor.ledger.merkle_root())
                if extra_headers:
                    for hk, hv in extra_headers.items():
                        self.send_header(hk, hv)
                self.end_headers()
                self.wfile.write(raw)

            def _send_text(self, status: int, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
                raw = text.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(raw)

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, traceparent")
                self.end_headers()

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                qs = parse_qs(parsed.query)
                gov = outer.gateway.governor

                if path in ("/", "/cockpit"):
                    from .cockpit import render_cockpit_html
                    self._send_text(200, render_cockpit_html(outer.gateway), "text/html; charset=utf-8")
                    return

                if path == "/healthz":
                    self._send_json(200, {"status": "healthy", "merkle_root": gov.ledger.merkle_root()})
                    return

                if path == "/metrics":
                    prom = gov.tracer.export_prometheus(
                        extra_gauges={
                            "switchback_ledger_merkle_size": float(len(gov.ledger)),
                            "switchback_active_tasks": float(len(gov.tasks())),
                        }
                    )
                    self._send_text(200, prom, "text/plain; version=0.0.4; charset=utf-8")
                    return

                if path == "/v1/traces/otlp":
                    self._send_json(200, gov.tracer.export_otlp_payload())
                    return

                if path == "/v1/audit/report":
                    task_filter = qs.get("task_id", [None])[0]
                    self._send_json(200, gov.ledger.generate_audit_report(task_id=task_filter))
                    return

                if path == "/api/overview":
                    from .cockpit import build_cockpit_overview
                    self._send_json(200, build_cockpit_overview(outer.gateway))
                    return

                self._send_json(404, {"error": f"Not found: {path}"})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    body = json.loads(raw_body.decode("utf-8"))
                except Exception:
                    self._send_json(400, {"error": "Invalid JSON body"})
                    return

                if path == "/v1/govern/intercept":
                    try:
                        res = outer.gateway.intercept(body)
                        self._send_json(
                            200,
                            res,
                            extra_headers={"X-Switchback-State": res["state"], "traceparent": res["traceparent"]},
                        )
                    except ErrSwitchbackTriggered as cb:
                        self._send_json(
                            cb.HTTP_STATUS,
                            cb.to_dict(),
                            extra_headers={"X-Switchback-State": cb.target_state.value},
                        )
                    return

                if path == "/v1/mcp/rpc":
                    resp = outer.gateway.mcp_server.handle_jsonrpc(body)
                    self._send_json(200, resp or {"jsonrpc": "2.0", "result": None})
                    return

                if path == "/api/intervene":
                    try:
                        res = outer.gateway.governor.human_intervene(
                            task_id=str(body["task_id"]),
                            human_actor=str(body.get("human_actor", "human-governor")),
                            governor_actor=str(body.get("governor_actor", "G-GOVERNOR")),
                            patched_payload=dict(body.get("patched_payload") or {}),
                            reason=str(body.get("reason", "Cockpit manual parameter patch & release")),
                        )
                        self._send_json(200, {"ok": True, **res})
                    except Exception as exc:
                        self._send_json(400, {"ok": False, "error": str(exc)})
                    return

                if path == "/api/rollback":
                    try:
                        res = outer.gateway.governor.rollback_to_km(
                            task_id=str(body["task_id"]),
                            target_km=int(body["target_km"]),
                            actor=str(body.get("actor", "human-governor")),
                            reason=str(body.get("reason", "Cockpit one-click Time Machine rollback")),
                        )
                        self._send_json(200, {"ok": True, **res})
                    except Exception as exc:
                        self._send_json(400, {"ok": False, "error": str(exc)})
                    return

                self._send_json(404, {"error": f"Not found: {path}"})

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.base_url

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
