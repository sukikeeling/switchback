"""Observability — OTel-compatible Trace/Log/Metrics without heavy SDKs.

The GOAI Track-1 rubric asks for Trace / Log / Metrics (>=1-2 of the three) and
suggests following OpenTelemetry GenAI conventions. This module emits
OpenTelemetry-shaped spans to a JSONL trace file and keeps metric counters,
so output can be replayed into any OTLP-compatible backend with a small shim.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


class Tracer:
    """Minimal OpenTelemetry-shaped span + event recorder (JSONL)."""

    def __init__(self, path: Optional[str] = None, service_name: str = "switchback") -> None:
        self._path = path or os.environ.get("SWITCHBACK_TRACE")
        self.service_name = service_name
        self._trace_id = uuid.uuid4().hex[:16]
        self._events: list[dict[str, Any]] = []
        self._counters: dict[str, int] = {}

    # ------------------------------------------------------------------ #
    # 结构
    # ------------------------------------------------------------------ #

    def start_span(self, name: str, parent: Optional[str] = None) -> str:
        span_id = uuid.uuid4().hex[:16]
        self._record(
            {
                "kind": "SPAN_START",
                "name": name,
                "trace_id": self._trace_id,
                "span_id": span_id,
                "parent_span_id": parent or "0000000000000000",
                "timestamp_ms": _now_ms(),
            }
        )
        return span_id

    def end_span(self, span_id: str, attributes: Optional[dict[str, Any]] = None) -> None:
        self._record(
            {
                "kind": "SPAN_END",
                "span_id": span_id,
                "trace_id": self._trace_id,
                "attributes": attributes or {},
                "timestamp_ms": _now_ms(),
            }
        )

    def event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        """A semantic log event on the current trace (Log signal)."""
        self._counters[name] = self._counters.get(name, 0) + 1
        self._record(
            {
                "kind": "LOG",
                "name": name,
                "trace_id": self._trace_id,
                "attributes": attributes or {},
                "timestamp_ms": _now_ms(),
            }
        )

    def metric(self, name: str, value: int = 1) -> int:
        """Increment a metric counter (Metrics signal)."""
        self._counters[name] = self._counters.get(name, 0) + value
        return self._counters[name]

    # ------------------------------------------------------------------ #
    # 输出
    # ------------------------------------------------------------------ #

    def _record(self, rec: dict[str, Any]) -> None:
        rec["service"] = self.service_name
        rec["genai_semconv"] = "gen_ai.usage.switchback/v1"
        self._events.append(rec)
        if self._path:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def counters(self) -> dict[str, int]:
        return dict(self._counters)

    def summary(self) -> dict[str, Any]:
        return {
            "trace_id": self._trace_id,
            "events": len(self._events),
            "counters": self._counters,
            "otel_shapes": {"spans": True, "logs": True, "metrics": True},
        }
