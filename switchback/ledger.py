"""K-marker ledger — the immutable, content-addressed, hash-chained & Merkle-tree
evidence book with SQLite WAL atomic persistence.

Every data update, recalculation, or release seals a new K-marker (K标版本).
The chain is both sequentially hash-linked (`prev_sha`) and anchored in a
domain-separated SHA-256 Merkle Tree (`merkle_root`): tampering with any entry
breaks both the sequential chain and the Merkle Root, making the ledger
provably auditable end to end with O(log N) inclusion proofs.

Supports both JSON file persistence and SQLite WAL atomic storage (using stdlib
``sqlite3`` + ``threading.RLock`` concurrency control).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional

from .merkle import MerkleProof, MerkleTree
from .protocol import KMarker, LedgerIntegrityError, _digest


def _is_sqlite_path(path: Optional[str]) -> bool:
    if not path:
        return False
    lower = path.lower()
    return lower.endswith((".db", ".sqlite", ".sqlite3"))


class KMarkerLedger:
    """Append-only, hash-chained & Merkle-anchored K-marker book.

    Supports:
      * Pure in-memory operation (`path=None`)
      * JSON persistence (`path=".../kmarker-ledger.json"`)
      * SQLite WAL atomic persistence (`path=".../kmarker-ledger.db"` or `sqlite_path=...`)
    """

    def __init__(
        self,
        path: Optional[str] = None,
        sqlite_path: Optional[str] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._entries: list[KMarker] = []
        self._path = path
        self._sqlite_path = sqlite_path or (path if _is_sqlite_path(path) else None)
        self._sealed_merkle_root: Optional[str] = None

        if self._sqlite_path:
            self._init_sqlite(self._sqlite_path)
            self._load_sqlite(self._sqlite_path)
        elif path and os.path.exists(path):
            self._load(path)

    # ------------------------------------------------------------------ #
    # 写入（带并发锁与原子落盘）
    # ------------------------------------------------------------------ #

    def append(self, task_id: str, label: str, payload: dict[str, Any]) -> KMarker:
        with self._lock:
            prev_sha = self._entries[-1].sha256 if self._entries else ""
            km = (self._entries[-1].km + 1) if self._entries else 0
            # Snapshot copy of payload to prevent accidental caller mutation
            payload_copy = json.loads(json.dumps(payload, ensure_ascii=False))
            marker = KMarker(km=km, task_id=task_id, label=label, payload=payload_copy).seal(prev_sha)
            self._entries.append(marker)
            self._sealed_merkle_root = self._build_merkle().root

            if self._sqlite_path:
                self._append_sqlite(self._sqlite_path, marker, self._sealed_merkle_root)
            if self._path and not _is_sqlite_path(self._path):
                self.save(self._path)
            return marker

    # ------------------------------------------------------------------ #
    # 读取 / 哈希链 + Merkle 树校验
    # ------------------------------------------------------------------ #

    def entries(self) -> list[KMarker]:
        with self._lock:
            return list(self._entries)

    def entries_for_task(self, task_id: str) -> list[KMarker]:
        with self._lock:
            return [m for m in self._entries if m.task_id == task_id]

    def get_km(self, km: int) -> KMarker:
        with self._lock:
            for m in self._entries:
                if m.km == km:
                    return m
            raise LedgerIntegrityError(f"K-marker K{km} not found in ledger")

    def last_km_for(self, task_id: str) -> Optional[int]:
        with self._lock:
            for m in reversed(self._entries):
                if m.task_id == task_id:
                    return m.km
            return None

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _build_merkle(self) -> MerkleTree:
        return MerkleTree([m.sha256 for m in self._entries])

    def merkle_root(self) -> str:
        """Compute the live Merkle Root over all K-marker entries."""
        with self._lock:
            if not self._entries:
                return ""
            # Recompute leaf digests from actual entry content so any in-memory
            # tampering of payload or sha256 changes the computed root vs sealed root.
            live_digests: list[str] = []
            for m in self._entries:
                body = {
                    "km": m.km,
                    "task_id": m.task_id,
                    "label": m.label,
                    "payload": m.payload,
                    "prev_sha": m.prev_sha,
                    "timestamp": m.timestamp,
                }
                live_digests.append(_digest(body))
            return MerkleTree(live_digests).root

    def merkle_proof(self, km: int) -> MerkleProof:
        """Generate an O(log N) Merkle inclusion proof for entry K{km}."""
        with self._lock:
            self.verify_chain()
            idx = None
            for i, m in enumerate(self._entries):
                if m.km == km:
                    idx = i
                    break
            if idx is None:
                raise LedgerIntegrityError(f"K-marker K{km} not found for Merkle proof")
            tree = self._build_merkle()
            return tree.get_proof(idx)

    def verify_merkle_proof(self, km: int, proof: Optional[MerkleProof] = None) -> bool:
        """Verify a Merkle inclusion proof against the ledger's Merkle Root."""
        with self._lock:
            self.verify_chain()
            marker = self.get_km(km)
            target_proof = proof if proof is not None else self.merkle_proof(km)
            if target_proof.leaf_hash != marker.sha256:
                raise LedgerIntegrityError(f"K-marker K{km}: Merkle proof leaf_hash mismatch")
            root = self.merkle_root()
            if not MerkleTree.verify_proof(target_proof, expected_root=root):
                raise LedgerIntegrityError(f"K-marker K{km}: Merkle proof verification failed against root {root[:16]}")
            return True

    def verify_chain(self) -> bool:
        """Recompute every digest, sequential linkage, and Merkle Root; raise on first break."""
        with self._lock:
            prev = ""
            for expected_km, m in enumerate(self._entries):
                if m.km != expected_km:
                    raise LedgerIntegrityError(f"K-marker sequence gap: expected K{expected_km}, got K{m.km}")
                if m.prev_sha != prev:
                    raise LedgerIntegrityError(f"K-marker {m.km}: broken link (prev_sha mismatch)")
                body = {
                    "km": m.km,
                    "task_id": m.task_id,
                    "label": m.label,
                    "payload": m.payload,
                    "prev_sha": m.prev_sha,
                    "timestamp": m.timestamp,
                }
                recomputed = _digest(body)
                if recomputed != m.sha256:
                    raise LedgerIntegrityError(f"K-marker {m.km}: digest mismatch (tampered)")
                prev = m.sha256

            if self._entries and self._sealed_merkle_root:
                current_root = self._build_merkle().root
                if current_root != self._sealed_merkle_root:
                    raise LedgerIntegrityError(
                        f"Merkle root mismatch: expected {self._sealed_merkle_root[:16]}, got {current_root[:16]}"
                    )
            return True

    # ------------------------------------------------------------------ #
    # 持久化：JSON 与 SQLite WAL 原子存储
    # ------------------------------------------------------------------ #

    def save(self, path: str) -> None:
        with self._lock:
            if _is_sqlite_path(path):
                self._init_sqlite(path)
                for m in self._entries:
                    self._append_sqlite(path, m, self._build_merkle().root)
                return
            root = self._build_merkle().root if self._entries else ""
            data = {
                "schema": "switchback.kmarker-ledger/v1",
                "merkle_root": root,
                "entries": [m.to_dict() for m in self._entries],
            }
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)

    def _load(self, path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for e in data.get("entries", []):
            m = KMarker(
                km=e["km"],
                id=e["id"],
                task_id=e["task_id"],
                label=e["label"],
                payload=e["payload"],
                prev_sha=e["prev_sha"],
                sha256=e["sha256"],
                timestamp=e["timestamp"],
            )
            self._entries.append(m)
        self._sealed_merkle_root = data.get("merkle_root") or (
            self._build_merkle().root if self._entries else None
        )

    def _init_sqlite(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=15.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kmarkers (
                    km INTEGER PRIMARY KEY,
                    id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    prev_sha TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    merkle_root TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _append_sqlite(self, db_path: str, marker: KMarker, merkle_root: str) -> None:
        conn = sqlite3.connect(db_path, timeout=15.0)
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                INSERT OR REPLACE INTO kmarkers
                (km, id, task_id, label, payload_json, prev_sha, sha256, timestamp, merkle_root)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    marker.km,
                    marker.id,
                    marker.task_id,
                    marker.label,
                    json.dumps(marker.payload, ensure_ascii=False, sort_keys=True),
                    marker.prev_sha,
                    marker.sha256,
                    marker.timestamp,
                    merkle_root,
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO ledger_meta (key, value) VALUES ('merkle_root', ?)",
                (merkle_root,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _load_sqlite(self, db_path: str) -> None:
        if not os.path.exists(db_path):
            return
        conn = sqlite3.connect(db_path, timeout=15.0)
        try:
            cur = conn.execute(
                "SELECT km, id, task_id, label, payload_json, prev_sha, sha256, timestamp FROM kmarkers ORDER BY km ASC"
            )
            rows = cur.fetchall()
            for km, mid, task_id, label, payload_json, prev_sha, sha256, ts in rows:
                self._entries.append(
                    KMarker(
                        km=int(km),
                        id=str(mid),
                        task_id=str(task_id),
                        label=str(label),
                        payload=json.loads(payload_json),
                        prev_sha=str(prev_sha),
                        sha256=str(sha256),
                        timestamp=str(ts),
                    )
                )
            meta_cur = conn.execute("SELECT value FROM ledger_meta WHERE key = 'merkle_root'")
            meta_row = meta_cur.fetchone()
            if meta_row:
                self._sealed_merkle_root = str(meta_row[0])
            elif self._entries:
                self._sealed_merkle_root = self._build_merkle().root
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # 导出与具备法律效力的机器行为审计报告（Audit Report）
    # ------------------------------------------------------------------ #

    def generate_audit_report(self, task_id: Optional[str] = None) -> dict[str, Any]:
        """Generate a tamper-evident machine behavior audit report with Merkle proofs."""
        with self._lock:
            chain_ok = self.verify_chain()
            tree = self._build_merkle()
            root = tree.root
            selected_entries = []
            for idx, m in enumerate(self._entries):
                if task_id and m.task_id != task_id:
                    continue
                proof = tree.get_proof(idx)
                selected_entries.append({
                    "marker": m.to_dict(),
                    "merkle_proof": proof.to_dict(),
                    "proof_verified": MerkleTree.verify_proof(proof, expected_root=root),
                })
            body = {
                "schema": "switchback.audit-report/v1",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "chain_integrity": chain_ok,
                "merkle_root": root,
                "tree_size": tree.size,
                "tree_height": tree.height,
                "task_filter": task_id,
                "entries_count": len(selected_entries),
                "entries": selected_entries,
            }
            body["report_sha256"] = _digest(body)
            return body

    def export(self, fmt: str = "json") -> str:
        with self._lock:
            root = self._build_merkle().root if self._entries else ""
            if fmt == "json":
                return json.dumps(
                    {
                        "schema": "switchback.kmarker-ledger/v1",
                        "merkle_root": root,
                        "entries": [m.to_dict() for m in self._entries],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            lines = ["| km | task | label | sha256 | prev |"]
            lines.append("|----|------|-------|--------|------|")
            for m in self._entries:
                lines.append(
                    f"| K{m.km} | {m.task_id} | {m.label} | {m.sha256[:10]}… | {m.prev_sha[:10]}… |"
                )
            if root:
                lines.append(f"\nMerkle Root: `{root}`")
            return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 风险台账 / 权利台账
# --------------------------------------------------------------------------- #

class RiskLedger:
    """Structured risk register — the risk.json equivalent for agent runs."""

    def __init__(self) -> None:
        self._risks: list[dict[str, Any]] = []

    def add(
        self,
        risk_id: str,
        title: str,
        score: int,
        note: str,
        mitigation: str,
        human_review: str,
    ) -> dict[str, Any]:
        entry = {
            "id": risk_id,
            "title": title,
            "score": score,
            "note": note,
            "mitigation": mitigation,
            "human_review": human_review,
        }
        if score >= 4:
            entry["flag"] = "mandatory_human_review"  # 高风险必须人工复核
        self._risks.append(entry)
        return entry

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "switchback.risk-ledger/v1", "risks": self._risks}

    def highest(self) -> list[dict[str, Any]]:
        return sorted(self._risks, key=lambda r: r["score"], reverse=True)


class RightsLedger:
    """Asset-by-asset rights & provenance register."""

    def __init__(self) -> None:
        self._assets: list[dict[str, Any]] = []

    def add(self, asset_id: str, path: str, license: str, provenance: str, owner: str) -> dict[str, Any]:
        entry = {
            "id": asset_id,
            "path": path,
            "license": license,
            "provenance": provenance,
            "owner": owner,
        }
        self._assets.append(entry)
        return entry

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "switchback.rights-ledger/v1", "assets": self._assets}
