"""Shared state store + agent memory for the switchback pipeline.

GOAI Track-1 requires implementing at least two of four context mechanisms:
agent memory storage / knowledge-base RAG / shared state management /
trajectory observability. This module provides *shared state management* and
*agent memory storage* with a compact, dependency-free design:

  * SharedState   — typed shared context a Manager hands to Workers (task cards,
                    decisions, evidence refs). Versioned by K-marker.
  * AgentMemory   — append-only episodic memory per agent (what it did, what it
                    learned), with keyword retrieval — the seed of a RAG store.

Trajectory observability lives in :mod:`switchback.trace`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class SharedState:
    """A thin shared-context store. Manager writes, Workers read.

    Every write is stamped and can be linked to a K-marker, so downstream
    agents always know *which version of the facts* they are reading.
    """

    def __init__(self) -> None:
        self._kv: dict[str, dict[str, Any]] = {}

    def put(self, key: str, value: Any, km: Optional[int] = None) -> None:
        self._kv[key] = {"value": value, "km": km, "updated_at": _now()}

    def get(self, key: str, default: Any = None) -> Any:
        return self._kv.get(key, {}).get("value", default)

    def version_of(self, key: str) -> Optional[int]:
        return self._kv.get(key, {}).get("km")

    def snapshot(self) -> dict[str, Any]:
        return {k: v["value"] for k, v in self._kv.items()}

    def provenance(self) -> list[dict[str, Any]]:
        return [{"key": k, "km": v["km"], "updated_at": v["updated_at"]} for k, v in self._kv.items()]


@dataclass
class MemoryEntry:
    """One episodic memory record for an agent."""

    agent_id: str
    kind: str  # "fact" | "lesson" | "error" | "evidence"
    content: str
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "kind": self.kind,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at,
        }


class AgentMemory:
    """Append-only episodic memory, retrievable by keyword/tag.

    This is the seeding layer of a knowledge-base RAG: entries carry tags and
    provenance so a real vector index can be swapped in without redesigning the
    write path (protocol-compatible migration, per the rubric).
    """

    def __init__(self) -> None:
        self._entries: list[MemoryEntry] = []

    def remember(self, agent_id: str, kind: str, content: str, tags: Optional[list[str]] = None) -> MemoryEntry:
        entry = MemoryEntry(agent_id=agent_id, kind=kind, content=content, tags=tags or [])
        self._entries.append(entry)
        return entry

    def recall(self, query: str, agent_id: Optional[str] = None, top_k: int = 5) -> list[MemoryEntry]:
        """Simple keyword/tag retrieval (a tiny lexical RAG for the demo)."""
        q = query.lower()
        scored: list[tuple[int, MemoryEntry]] = []
        for e in self._entries:
            if agent_id and e.agent_id != agent_id:
                continue
            hay = (e.content + " " + " ".join(e.tags)).lower()
            score = hay.count(q)
            if score:
                scored.append((score, e))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    def export(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._entries]
