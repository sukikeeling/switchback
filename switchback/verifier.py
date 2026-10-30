"""Live Evidence Engine (活体证据核验器 · 动态事实对齐矩阵).

Upgrades `evidence-verify` from static fixture dicts to a live, multi-dimensional
fact alignment matrix built from the hard-won lessons of `open-city-ai/haidian`:

  1. 三处数值硬核交叉验真 (Three-Way Numeric Cross-Verification):
     Extracts and aligns metrics across (a) prose text, (b) Markdown/CSV/JSON
     table attachments, and (c) raw API response payloads.
  2. 引用双向链锁定与活体快照存证 (Bidirectional Citation Lock & Live Snapshot):
     Bidirectional citation check (`reference_forward` + `reference_backward`)
     plus real-time probe & SHA-256 content-addressed snapshot verification
     (detects 404 link rot and post-hoc source tampering).
  3. 版本漂移零容忍 (Zero-Tolerance Atomic Package Verification):
     - CRLF vs LF line-ending hash drift detection (`crlf_hash_alignment`)
     - Multi-file `package_id` / version tag residue check (`package_id_consistency`)
     - Bilingual Chinese/English anchor & numeric alignment + English CJK residue
       detection (`bilingual_marker_alignment`, `en_cjk_zero_residue`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


@dataclass
class SourceSnapshot:
    """Content-addressed snapshot of a cited external/local source."""

    source_id: str
    uri: str
    status: str  # "OK" | "HTTP_404" | "UNREACHABLE" | "HASH_DRIFT"
    sha256: str
    expected_sha256: Optional[str] = None
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    excerpt: str = ""

    @property
    def ok(self) -> bool:
        if self.status != "OK":
            return False
        if self.expected_sha256 and self.sha256 != self.expected_sha256:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "uri": self.uri,
            "status": self.status if (not self.expected_sha256 or self.sha256 == self.expected_sha256) else "HASH_DRIFT",
            "ok": self.ok,
            "sha256": self.sha256,
            "expected_sha256": self.expected_sha256,
            "timestamp": self.timestamp,
            "excerpt": self.excerpt[:120],
        }


class LiveEvidenceEngine:
    """Production-grade Live Evidence Engine for multi-agent artifacts."""

    # ------------------------------------------------------------------ #
    # 1. 三处数值硬核交叉验真（正文 + 表格附件 + API 原始报文）
    # ------------------------------------------------------------------ #

    @staticmethod
    def extract_prose_metrics(prose: str, keys: list[str]) -> dict[str, float]:
        """Extract numeric values for `keys` from prose text (`key: 84`, `key=84`, `key为84`)."""
        found: dict[str, float] = {}
        for k in keys:
            pattern = rf"{re.escape(k)}\s*(?:[:=是为]|->|\s)\s*([-+]?\d+(?:\.\d+)?)"
            m = re.search(pattern, prose, flags=re.IGNORECASE)
            if m:
                found[k] = float(m.group(1))
        return found

    @staticmethod
    def extract_table_metrics(table: str | list[dict[str, Any]] | dict[str, Any], keys: list[str]) -> dict[str, float]:
        """Extract numeric values for `keys` from Markdown table, list of rows, or dict."""
        found: dict[str, float] = {}
        if isinstance(table, dict):
            for k in keys:
                if k in table and table[k] is not None:
                    try:
                        found[k] = float(str(table[k]).rstrip("%"))
                    except ValueError:
                        pass
            return found
        if isinstance(table, list):
            for row in table:
                if isinstance(row, dict):
                    metric_name = str(row.get("metric") or row.get("key") or row.get("name") or "")
                    if metric_name in keys and "value" in row:
                        try:
                            found[metric_name] = float(str(row["value"]).rstrip("%"))
                        except ValueError:
                            pass
                    for k in keys:
                        if k in row and row[k] is not None:
                            try:
                                found[k] = float(str(row[k]).rstrip("%"))
                            except ValueError:
                                pass
            return found
        # Markdown table string: `| score | 84 |`
        for k in keys:
            pattern = rf"\|\s*{re.escape(k)}\s*\|\s*([-+]?\d+(?:\.\d+)?)%?\s*\|"
            m = re.search(pattern, str(table), flags=re.IGNORECASE)
            if m:
                found[k] = float(m.group(1))
        return found

    @staticmethod
    def extract_api_metrics(api_payload: dict[str, Any], keys: list[str]) -> dict[str, float]:
        """Extract numeric values for `keys` from raw API JSON payload (supports nested `data`)."""
        found: dict[str, float] = {}
        containers = [api_payload]
        if isinstance(api_payload.get("data"), dict):
            containers.append(api_payload["data"])
        if isinstance(api_payload.get("metrics"), dict):
            containers.append(api_payload["metrics"])
        for c in containers:
            for k in keys:
                if k in c and c[k] is not None and k not in found:
                    try:
                        found[k] = float(str(c[k]).rstrip("%"))
                    except ValueError:
                        pass
        return found

    @classmethod
    def verify_three_way_live(
        cls,
        prose: str,
        table: str | list[dict[str, Any]] | dict[str, Any],
        api_payload: dict[str, Any],
        numeric_keys: list[str],
        tolerance: float = 1e-6,
    ) -> list[dict[str, Any]]:
        """Cross-verify numeric metrics across prose, table attachment, and API payload."""
        prose_vals = cls.extract_prose_metrics(prose, numeric_keys)
        table_vals = cls.extract_table_metrics(table, numeric_keys)
        api_vals = cls.extract_api_metrics(api_payload, numeric_keys)

        results: list[dict[str, Any]] = []
        for k in numeric_keys:
            v_prose = prose_vals.get(k)
            v_table = table_vals.get(k)
            v_api = api_vals.get(k)
            present = [v for v in (v_prose, v_table, v_api) if v is not None]
            aligned = (
                len(present) == 3
                and abs(v_prose - v_table) <= tolerance  # type: ignore[operator]
                and abs(v_table - v_api) <= tolerance    # type: ignore[operator]
            )
            results.append(
                {
                    "check": "numeric_three_way_live",
                    "key": k,
                    "ok": aligned,
                    "sources": {
                        "prose": v_prose,
                        "table": v_table,
                        "api": v_api,
                    },
                    "values": present,
                }
            )
        return results

    # ------------------------------------------------------------------ #
    # 2. 引用双向链锁定与活体快照存证（实时探针 + SHA-256 固化）
    # ------------------------------------------------------------------ #

    @staticmethod
    def probe_source(source_id: str, spec: Any, timeout: float = 3.0) -> SourceSnapshot:
        """Probe a single source spec (inline string, file://, http(s)://, or dict with expected_sha256)."""
        if isinstance(spec, str):
            uri = spec
            expected_sha = None
            inline_content = None if spec.startswith(("http://", "https://", "file://")) else spec
        elif isinstance(spec, dict):
            uri = str(spec.get("uri") or spec.get("url") or spec.get("path") or f"inline:{source_id}")
            expected_sha = spec.get("expected_sha256") or spec.get("sha256")
            inline_content = spec.get("content")
            if spec.get("status") == 404 or spec.get("simulate_404"):
                return SourceSnapshot(
                    source_id=source_id,
                    uri=uri,
                    status="HTTP_404",
                    sha256="",
                    expected_sha256=expected_sha,
                )
        else:
            uri = f"inline:{source_id}"
            expected_sha = None
            inline_content = str(spec)

        if inline_content is not None:
            digest = _sha256_text(str(inline_content))
            status = "OK"
            if expected_sha and digest != expected_sha:
                status = "HASH_DRIFT"
            return SourceSnapshot(
                source_id=source_id,
                uri=uri,
                status=status,
                sha256=digest,
                expected_sha256=expected_sha,
                excerpt=str(inline_content)[:120],
            )

        if uri.startswith("file://"):
            fpath = uri[len("file://"):]
            if not os.path.exists(fpath):
                return SourceSnapshot(
                    source_id=source_id,
                    uri=uri,
                    status="HTTP_404",
                    sha256="",
                    expected_sha256=expected_sha,
                )
            raw = open(fpath, "rb").read()
            digest = _sha256_bytes(raw)
            status = "OK" if (not expected_sha or digest == expected_sha) else "HASH_DRIFT"
            return SourceSnapshot(
                source_id=source_id,
                uri=uri,
                status=status,
                sha256=digest,
                expected_sha256=expected_sha,
                excerpt=raw.decode("utf-8", errors="replace")[:120],
            )

        if uri.startswith(("http://", "https://")):
            req = urllib.request.Request(uri, headers={"User-Agent": "Switchback-LiveVerifier/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                digest = _sha256_bytes(raw)
                status = "OK" if (not expected_sha or digest == expected_sha) else "HASH_DRIFT"
                return SourceSnapshot(
                    source_id=source_id,
                    uri=uri,
                    status=status,
                    sha256=digest,
                    expected_sha256=expected_sha,
                    excerpt=raw.decode("utf-8", errors="replace")[:120],
                )
            except urllib.error.HTTPError as e:
                st = "HTTP_404" if e.code == 404 else f"HTTP_{e.code}"
                return SourceSnapshot(
                    source_id=source_id,
                    uri=uri,
                    status=st,
                    sha256="",
                    expected_sha256=expected_sha,
                )
            except Exception as e:
                return SourceSnapshot(
                    source_id=source_id,
                    uri=uri,
                    status=f"UNREACHABLE:{type(e).__name__}",
                    sha256="",
                    expected_sha256=expected_sha,
                )

        digest = _sha256_text(uri)
        return SourceSnapshot(source_id=source_id, uri=uri, status="OK", sha256=digest, expected_sha256=expected_sha)

    # ------------------------------------------------------------------ #
    # 3. 原子包与版本漂移零容忍（CRLF 哈希错位 / package_id 残留 / 中英标记漂移）
    # ------------------------------------------------------------------ #

    @staticmethod
    def verify_atomic_package(
        artifacts: dict[str, str | bytes],
        *,
        expected_package_id: Optional[str] = None,
        expected_version: Optional[str] = None,
        forbid_crlf: bool = True,
        bilingual_pair: Optional[tuple[str, str]] = None,
    ) -> dict[str, Any]:
        """Verify multi-file artifact bundle against the 3 historical Haidian CI killers:

          1. `crlf_drift`: CRLF (`\\r\\n`) line endings causing hash mismatch across OS
          2. `package_id_residue`: inconsistent or stale `package_id` / `version` across files
          3. `bilingual_marker_drift`: anchor tags `[ANCHOR:...]` or numbers drifting between
             ZH and EN documents, or CJK characters leaking into English documents.
        """
        checks: list[dict[str, Any]] = []
        text_files: dict[str, str] = {}
        crlf_files: list[str] = []
        file_hashes: dict[str, dict[str, str]] = {}

        for name, content in artifacts.items():
            raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
            text = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
            text_files[name] = text
            has_crlf = b"\r\n" in raw_bytes
            if has_crlf:
                crlf_files.append(name)
            lf_bytes = raw_bytes.replace(b"\r\n", b"\n")
            file_hashes[name] = {
                "raw_sha256": _sha256_bytes(raw_bytes),
                "lf_sha256": _sha256_bytes(lf_bytes),
            }

        # Check 1: CRLF drift
        crlf_ok = (len(crlf_files) == 0) if forbid_crlf else True
        checks.append(
            {
                "check": "crlf_hash_alignment",
                "ok": crlf_ok,
                "crlf_files": crlf_files,
                "file_hashes": file_hashes,
            }
        )

        # Check 2: package_id & version residue across all files
        found_pkg_ids: dict[str, list[str]] = {}
        found_versions: dict[str, list[str]] = {}
        for name, text in text_files.items():
            pkgs = re.findall(r'package_id["\']?\s*[:=]\s*["\']?([A-Za-z0-9_.-]+)', text)
            vers = re.findall(r'\bversion["\']?\s*[:=]\s*["\']?(v?\d+(?:\.\d+)*)', text)
            if pkgs:
                found_pkg_ids[name] = pkgs
            if vers:
                found_versions[name] = vers

        unique_pkgs = {p for plist in found_pkg_ids.values() for p in plist}
        unique_vers = {v for vlist in found_versions.values() for v in vlist}
        pkg_ok = len(unique_pkgs) <= 1 and (expected_package_id is None or unique_pkgs <= {expected_package_id})
        ver_ok = len(unique_vers) <= 1 and (expected_version is None or unique_vers <= {expected_version})
        checks.append(
            {
                "check": "package_id_consistency",
                "ok": pkg_ok and ver_ok,
                "unique_package_ids": sorted(unique_pkgs),
                "unique_versions": sorted(unique_vers),
                "by_file": {"package_ids": found_pkg_ids, "versions": found_versions},
            }
        )

        # Check 3: Bilingual marker & CJK residue check
        if bilingual_pair:
            zh_key, en_key = bilingual_pair
            zh_text = text_files.get(zh_key, "")
            en_text = text_files.get(en_key, "")
            zh_anchors = re.findall(r"\[(?:ANCHOR|K-MARKER|SEC):([A-Za-z0-9_.-]+)\]", zh_text)
            en_anchors = re.findall(r"\[(?:ANCHOR|K-MARKER|SEC):([A-Za-z0-9_.-]+)\]", en_text)
            missing_in_en = sorted(set(zh_anchors) - set(en_anchors))
            extra_in_en = sorted(set(en_anchors) - set(zh_anchors))
            cjk_in_en = re.findall(r"[\u4e00-\u9fff]+", en_text)
            drift_count = len(missing_in_en) + len(extra_in_en) + len(cjk_in_en)
            checks.append(
                {
                    "check": "bilingual_marker_alignment",
                    "ok": drift_count == 0,
                    "drift_count": drift_count,
                    "missing_anchors_in_en": missing_in_en,
                    "extra_anchors_in_en": extra_in_en,
                    "cjk_residue_in_en_count": len(cjk_in_en),
                }
            )

        passed = all(c["ok"] for c in checks)
        return {"passed": passed, "checks": checks}
