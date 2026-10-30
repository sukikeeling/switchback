"""Merkle Tree permanent evidence chain for the Switchback K-Marker Ledger.

Provides RFC-6962-inspired domain-separated SHA-256 Merkle trees over K-marker
digests, enabling O(log N) cryptographic inclusion proofs and tamper-evident
root hashes for legal/compliance machine behavior audit reports.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional


def _hash_leaf(leaf_digest: str) -> str:
    """Domain-separated leaf hash (0x00 prefix)."""
    h = hashlib.sha256()
    h.update(b"\x00")
    h.update(leaf_digest.encode("utf-8"))
    return h.hexdigest()


def _hash_nodes(left: str, right: str) -> str:
    """Domain-separated internal node hash (0x01 prefix)."""
    h = hashlib.sha256()
    h.update(b"\x01")
    h.update(left.encode("utf-8"))
    h.update(b":")
    h.update(right.encode("utf-8"))
    return h.hexdigest()


@dataclass
class MerkleProof:
    """Cryptographic inclusion proof for a single K-marker in the Merkle tree."""

    leaf_index: int
    leaf_hash: str
    siblings: list[dict[str, str]]  # [{"position": "left"|"right", "hash": "..."}]
    root_hash: str
    tree_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "leaf_index": self.leaf_index,
            "leaf_hash": self.leaf_hash,
            "siblings": list(self.siblings),
            "root_hash": self.root_hash,
            "tree_size": self.tree_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MerkleProof":
        return cls(
            leaf_index=int(data["leaf_index"]),
            leaf_hash=str(data["leaf_hash"]),
            siblings=list(data["siblings"]),
            root_hash=str(data["root_hash"]),
            tree_size=int(data["tree_size"]),
        )


class MerkleTree:
    """Deterministic binary Merkle Tree over K-marker SHA-256 digests."""

    def __init__(self, leaf_digests: list[str]) -> None:
        self._raw_leaves = list(leaf_digests)
        self._levels: list[list[str]] = []
        if self._raw_leaves:
            self._build()

    def _build(self) -> None:
        current = [_hash_leaf(d) for d in self._raw_leaves]
        self._levels = [current]
        while len(current) > 1:
            next_level: list[str] = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i + 1] if (i + 1) < len(current) else current[i]
                next_level.append(_hash_nodes(left, right))
            self._levels.append(next_level)
            current = next_level

    @property
    def root(self) -> str:
        if not self._levels:
            return ""
        return self._levels[-1][0]

    @property
    def size(self) -> int:
        return len(self._raw_leaves)

    @property
    def height(self) -> int:
        return len(self._levels)

    def get_proof(self, index: int) -> MerkleProof:
        if index < 0 or index >= len(self._raw_leaves):
            raise IndexError(f"Merkle leaf index {index} out of range (size={len(self._raw_leaves)})")
        siblings: list[dict[str, str]] = []
        idx = index
        for level in self._levels[:-1]:
            if idx % 2 == 0:
                sib_idx = idx + 1 if (idx + 1) < len(level) else idx
                siblings.append({"position": "right", "hash": level[sib_idx]})
            else:
                sib_idx = idx - 1
                siblings.append({"position": "left", "hash": level[sib_idx]})
            idx //= 2
        return MerkleProof(
            leaf_index=index,
            leaf_hash=self._raw_leaves[index],
            siblings=siblings,
            root_hash=self.root,
            tree_size=self.size,
        )

    @staticmethod
    def verify_proof(proof: MerkleProof, expected_root: Optional[str] = None) -> bool:
        """Recompute root from leaf_hash and sibling path; compare to expected_root."""
        target_root = expected_root if expected_root is not None else proof.root_hash
        if not target_root:
            return False
        current = _hash_leaf(proof.leaf_hash)
        for step in proof.siblings:
            pos = step.get("position")
            sib_hash = step.get("hash", "")
            if pos == "right":
                current = _hash_nodes(current, sib_hash)
            elif pos == "left":
                current = _hash_nodes(sib_hash, current)
            else:
                return False
        return current == target_root
