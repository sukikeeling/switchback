"""Observability — Industrial OTel / OTLP Exporter, W3C TraceContext, Prometheus
Metrics, and Millisecond Causal Decision Tree without external runtime dependencies.

Implements:
  * JSONL OTel-shaped event stream (backward-compatible with v0.1)
  * W3C TraceContext (`traceparent` 00-<32hex>-<16hex>-01) propagation
  * OpenTelemetry Protocol (OTLP/HTTP JSON) `resourceSpans` exporter for Jaeger/Tempo
  * Prometheus text exposition format (`/metrics`) for Grafana rail topology dashboards
  * Causal Decision Tree reconstruction (`build_causal_tree`) for Human Governor review
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


def _now_ns() -> int:
    return time.time_ns()


def _to_otel_attributes(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a Python dict to OTLP JSON KeyValue list."""
    out: list[dict[str, Any]] = []
    for k, v in attrs.items():
        if isinstance(v, bool):
            val = {"boolValue": v}
        elif isinstance(v, int):
            val = {"intValue": str(v)}
        elif isinstance(v, float):
            val = {"doubleValue": v}
        else:
            val = {"stringValue": str(v) if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)}
        out.append({"key": str(k), "value": val})
    return out


class Tracer:
    """OpenTelemetry / OTLP span, log & Prometheus metrics recorder."""

    def __init__(
        self,
        path: Optional[str] = None,
        service_name: str = "switchback",
        otlp_endpoint: Optional[str] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._path = path or os.environ.get("SWITCHBACK_TRACE")
        self.service_name = service_name
        self.otlp_endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        # 32-hex (128-bit) W3C trace_id
        self._trace_id = uuid.uuid4().hex
        self._events: list[dict[str, Any]] = []
        self._counters: dict[str, int] = {}
        self._open_spans: dict[str, dict[str, Any]] = {}
        self._completed_spans: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    # W3C TraceContext 传播
    # ------------------------------------------------------------------ #

    def traceparent(self, span_id: Optional[str] = None) -> str:
        """Format a W3C TraceContext `traceparent` header."""
        sid = (span_id or "0000000000000001")[:16].ljust(16, "0")
        tid = self._trace_id[:32].ljust(32, "0")
        return f"00-{tid}-{sid}-01"

    @staticmethod
    def parse_traceparent(header: str) -> Optional[tuple[str, str]]:
        """Parse `00-<trace_id_32>-<span_id_16>-<flags>` into (trace_id, parent_span_id)."""
        if not header:
            return None
        parts = header.strip().split("-")
        if len(parts) != 4:
            return None
        _, trace_id, span_id, _ = parts
        if len(trace_id) == 32 and len(span_id) == 16:
            return trace_id, span_id
        return None

    # ------------------------------------------------------------------ #
    # Span / Event / Metric 记录
    # ------------------------------------------------------------------ #

    def start_span(
        self,
        name: str,
        parent: Optional[str] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> str:
        with self._lock:
            span_id = uuid.uuid4().hex[:16]
            parent_id = parent or "0000000000000000"
            ts_ms = _now_ms()
            ts_ns = _now_ns()
            span_meta = {
                "name": name,
                "trace_id": self._trace_id,
                "span_id": span_id,
                "parent_span_id": parent_id,
                "start_ms": ts_ms,
                "start_ns": ts_ns,
                "attributes": dict(attributes or {}),
                "events": [],
            }
            self._open_spans[span_id] = span_meta
            self._counters["spans.started"] = self._counters.get("spans.started", 0) + 1
            self._record(
                {
                    "kind": "SPAN_START",
                    "name": name,
                    "trace_id": self._trace_id,
                    "span_id": span_id,
                    "parent_span_id": parent_id,
                    "attributes": dict(attributes or {}),
                    "timestamp_ms": ts_ms,
                }
            )
            return span_id

    def end_span(
        self,
        span_id: str,
        attributes: Optional[dict[str, Any]] = None,
        status_code: str = "OK",
    ) -> None:
        with self._lock:
            ts_ms = _now_ms()
            ts_ns = _now_ns()
            merged_attrs = dict(attributes or {})
            if span_id in self._open_spans:
                meta = self._open_spans.pop(span_id)
                meta["end_ms"] = ts_ms
                meta["end_ns"] = max(ts_ns, meta["start_ns"] + 1000)
                meta["duration_ms"] = max(0, ts_ms - meta["start_ms"])
                meta["attributes"].update(merged_attrs)
                meta["status_code"] = status_code
                self._completed_spans.append(meta)
            self._counters["spans.ended"] = self._counters.get("spans.ended", 0) + 1
            self._record(
                {
                    "kind": "SPAN_END",
                    "span_id": span_id,
                    "trace_id": self._trace_id,
                    "attributes": merged_attrs,
                    "status_code": status_code,
                    "timestamp_ms": ts_ms,
                }
            )

    def event(
        self,
        name: str,
        attributes: Optional[dict[str, Any]] = None,
        span_id: Optional[str] = None,
    ) -> None:
        """A semantic log event on the current trace (Log signal)."""
        with self._lock:
            ts_ms = _now_ms()
            ts_ns = _now_ns()
            attrs = dict(attributes or {})
            self._counters[name] = self._counters.get(name, 0) + 1
            if span_id and span_id in self._open_spans:
                self._open_spans[span_id]["events"].append(
                    {"name": name, "timestamp_ns": ts_ns, "attributes": attrs}
                )
            self._record(
                {
                    "kind": "LOG",
                    "name": name,
                    "trace_id": self._trace_id,
                    "span_id": span_id or "0000000000000000",
                    "attributes": attrs,
                    "timestamp_ms": ts_ms,
                }
            )

    def metric(self, name: str, value: int = 1) -> int:
        """Increment a metric counter (Metrics signal)."""
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + value
            return self._counters[name]

    # ------------------------------------------------------------------ #
    # OTLP / HTTP JSON 导出与推送（对接 Jaeger / Grafana Tempo）
    # ------------------------------------------------------------------ #

    def export_otlp_payload(self) -> dict[str, Any]:
        """Export recorded spans and log events in standard OpenTelemetry OTLP/JSON schema."""
        with self._lock:
            otlp_spans: list[dict[str, Any]] = []
            all_spans = list(self._completed_spans) + list(self._open_spans.values())
            for sp in all_spans:
                end_ns = sp.get("end_ns", sp["start_ns"] + 1_000_000)
                status_str = sp.get("status_code", "OK")
                otlp_spans.append(
                    {
                        "traceId": sp["trace_id"][:32].ljust(32, "0"),
                        "spanId": sp["span_id"][:16].ljust(16, "0"),
                        "parentSpanId": (
                            sp["parent_span_id"][:16].ljust(16, "0")
                            if sp.get("parent_span_id") and sp["parent_span_id"] != "0000000000000000"
                            else ""
                        ),
                        "name": sp["name"],
                        "kind": 1,  # SPAN_KIND_INTERNAL / SERVER
                        "startTimeUnixNano": str(sp["start_ns"]),
                        "endTimeUnixNano": str(end_ns),
                        "attributes": _to_otel_attributes(
                            {
                                "gen_ai.system": "switchback",
                                "gen_ai.usage.semconv": "gen_ai.usage.switchback/v1",
                                **sp.get("attributes", {}),
                            }
                        ),
                        "events": [
                            {
                                "timeUnixNano": str(ev["timestamp_ns"]),
                                "name": ev["name"],
                                "attributes": _to_otel_attributes(ev.get("attributes", {})),
                            }
                            for ev in sp.get("events", [])
                        ],
                        "status": {
                            "code": 1 if status_str == "OK" else 2,
                            "message": status_str,
                        },
                    }
                )

            # Also synthesize spans from standalone semantic events so every governance
            # decision appears on Jaeger / Tempo timelines even when called via event().
            for idx, ev in enumerate(self._events):
                if ev.get("kind") != "LOG":
                    continue
                ev_ns = int(ev.get("timestamp_ms", _now_ms())) * 1_000_000
                sid = hashlib.sha256_short(f"{self._trace_id}:{idx}:{ev['name']}")
                otlp_spans.append(
                    {
                        "traceId": self._trace_id[:32].ljust(32, "0"),
                        "spanId": sid,
                        "parentSpanId": (
                            ev["span_id"]
                            if ev.get("span_id") and ev["span_id"] != "0000000000000000"
                            else ""
                        ),
                        "name": ev["name"],
                        "kind": 1,
                        "startTimeUnixNano": str(ev_ns),
                        "endTimeUnixNano": str(ev_ns + 500_000),
                        "attributes": _to_otel_attributes(
                            {
                                "gen_ai.system": "switchback",
                                "switchback.event_kind": "governance_log",
                                **ev.get("attributes", {}),
                            }
                        ),
                        "status": {
                            "code": 2 if "circuit_break" in ev["name"] or "depot" in ev["name"] else 1
                        },
                    }
                )

            return {
                "resourceSpans": [
                    {
                        "resource": {
                            "attributes": _to_otel_attributes(
                                {
                                    "service.name": self.service_name,
                                    "service.version": "1.0.0",
                                    "telemetry.sdk.name": "switchback-otel-native",
                                    "telemetry.sdk.language": "python",
                                }
                            )
                        },
                        "scopeSpans": [
                            {
                                "scope": {
                                    "name": "switchback.governance.tracer",
                                    "version": "1.0.0",
                                },
                                "spans": otlp_spans,
                            }
                        ],
                    }
                ]
            }

    def push_otlp(self, endpoint: Optional[str] = None, timeout: float = 3.0) -> dict[str, Any]:
        """Push OTLP/JSON payload to an OTLP HTTP collector (`/v1/traces`)."""
        target = endpoint or self.otlp_endpoint
        payload = self.export_otlp_payload()
        if not target:
            return {"pushed": False, "reason": "no_endpoint_configured", "spans": len(payload["resourceSpans"][0]["scopeSpans"][0]["spans"])}
        url = target if target.endswith("/v1/traces") else target.rstrip("/") + "/v1/traces"
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=raw,
            headers={"Content-Type": "application/json", "User-Agent": "switchback-otlp-exporter/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {"pushed": True, "status": resp.status, "endpoint": url}
        except Exception as exc:
            return {"pushed": False, "endpoint": url, "error": str(exc)}

    # ------------------------------------------------------------------ #
    # Prometheus Metrics 导出（供 Grafana 轨道拓扑大屏拉取）
    # ------------------------------------------------------------------ #

    def export_prometheus(self, extra_gauges: Optional[dict[str, float]] = None) -> str:
        """Render metrics in standard Prometheus text exposition format."""
        with self._lock:
            lines: list[str] = [
                "# HELP switchback_events_total Total governance semantic events by name",
                "# TYPE switchback_events_total counter",
            ]
            for name, count in sorted(self._counters.items()):
                safe_label = name.replace('"', '\\"')
                lines.append(
                    f'switchback_events_total{{service="{self.service_name}",event="{safe_label}"}} {count}'
                )

            mainline_cnt = self._counters.get("task.mainline", 0)
            siding_cnt = self._counters.get("task.siding", 0)
            depot_cnt = self._counters.get("task.depot", 0)
            cb_cnt = self._counters.get("sidecar.circuit_break", 0)
            sealed_cnt = self._counters.get("ledger.sealed", 0)

            lines.extend(
                [
                    "# HELP switchback_state_transitions_total Total switch state transitions",
                    "# TYPE switchback_state_transitions_total counter",
                    f'switchback_state_transitions_total{{state="mainline"}} {mainline_cnt}',
                    f'switchback_state_transitions_total{{state="siding"}} {siding_cnt}',
                    f'switchback_state_transitions_total{{state="depot"}} {depot_cnt}',
                    "# HELP switchback_circuit_breaks_total Total hard circuit breaks at Sidecar",
                    "# TYPE switchback_circuit_breaks_total counter",
                    f"switchback_circuit_breaks_total {cb_cnt}",
                    "# HELP switchback_kmarkers_sealed_total Total K-markers sealed",
                    "# TYPE switchback_kmarkers_sealed_total counter",
                    f"switchback_kmarkers_sealed_total {sealed_cnt}",
                ]
            )
            if extra_gauges:
                for g_name, g_val in sorted(extra_gauges.items()):
                    metric_id = g_name.replace(".", "_").replace("-", "_")
                    lines.append(f"# TYPE {metric_id} gauge")
                    lines.append(f"{metric_id} {g_val}")
            return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------ #
    # 因果决策树回放（Causal Decision Trace Tree）
    # ------------------------------------------------------------------ #

    def build_causal_tree(self, task_id: Optional[str] = None) -> dict[str, Any]:
        """Build a chronological & hierarchical causal trace for Human Governor inspection."""
        with self._lock:
            timeline: list[dict[str, Any]] = []
            for ev in self._events:
                attrs = ev.get("attributes", {})
                ev_task = attrs.get("task_id")
                if task_id and ev_task != task_id:
                    continue
                timeline.append(
                    {
                        "kind": ev.get("kind"),
                        "name": ev.get("name"),
                        "span_id": ev.get("span_id", "0000000000000000"),
                        "timestamp_ms": ev.get("timestamp_ms"),
                        "attributes": attrs,
                    }
                )
            return {
                "trace_id": self._trace_id,
                "service": self.service_name,
                "task_filter": task_id,
                "node_count": len(timeline),
                "timeline": timeline,
            }

    # ------------------------------------------------------------------ #
    # 内部与输出
    # ------------------------------------------------------------------ #

    def _record(self, rec: dict[str, Any]) -> None:
        rec["service"] = self.service_name
        rec["genai_semconv"] = "gen_ai.usage.switchback/v1"
        self._events.append(rec)
        if self._path:
            os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def counters(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "trace_id": self._trace_id,
                "events": len(self._events),
                "counters": dict(self._counters),
                "otel_shapes": {"spans": True, "logs": True, "metrics": True, "otlp_json": True, "prometheus": True},
            }


class hashlib:
    """Helper namespace for short deterministic span IDs."""

    @staticmethod
    def sha256_short(val: str) -> str:
        import hashlib as _hl
        return _hl.sha256(val.encode("utf-8")).hexdigest()[:16]
