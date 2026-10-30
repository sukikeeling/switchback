"""Switchback Governance (折返治理 · Industrial Production Guardrail v1.0).

The production-grade human-in-the-loop governance & sidecar circuit-breaker
framework for multi-agent teams.

Modeled on the "Ren-shaped" (人字形) switchback line at Qinglongqiao on the
Centennial Jingzhang Railway: a train climbing a steep grade must stop at a
switchback node, change direction, and continue only after a three-party review
decides *pass / turn back / pull into depot*. No scenario continues automatically.

Core Mechanisms & Production Modules:
  1. Switchback Node      — fixed checkpoints where any party's veto forces a turn-back.
  2. Grade-based Access   — dynamic risk grading (gentle / medium / steep).
  3. K-marker Ledger      — immutable SHA-256 hash chain + Merkle Tree + SQLite WAL.
  4. Switch States        — mainline / siding / depot, with **no automatic recovery**,
                            anti-retry loop guard, and exploration budget enforcement.
  5. Live Sidecar Gateway — inline HTTP / JSON-RPC / MCP proxy with physical hard
                            circuit breaker (`ErrSwitchbackTriggered`).
  6. Live Evidence Engine — 3-way numeric cross-verification, bidirectional citation
                            snapshot lock, and atomic package drift guard.
  7. Human Cockpit WebUI  — dual-signature release & one-click Time Machine rollback.
"""

from __future__ import annotations

__version__ = "1.0.0"
__all__ = [
    "__version__",
    "Grade",
    "SwitchState",
    "Verdict",
    "PartyRole",
    "CheckpointKind",
    "Checkpoint",
    "KMarker",
    "SwitchbackError",
    "GradeAccessError",
    "NoAutoResumeError",
    "AntiRetryLoopError",
    "BudgetExhaustedError",
    "LedgerIntegrityError",
    "ErrSwitchbackTriggered",
    "SwitchbackGovernor",
    "KMarkerLedger",
    "RiskLedger",
    "RightsLedger",
    "MerkleTree",
    "MerkleProof",
    "Tracer",
    "LiveEvidenceEngine",
    "SourceSnapshot",
    "SwitchbackSidecarGateway",
    "SidecarHTTPServer",
    "ConsumerTokenVault",
    "SwitchbackMCPServer",
    "AgentTeamsCluster",
    "MatrixRoomBus",
    "AGENTTEAMS_ROSTER",
    "build_cockpit_overview",
    "render_cockpit_html",
    "format_im_card",
]

from .protocol import (
    Grade,
    SwitchState,
    Verdict,
    PartyRole,
    CheckpointKind,
    Checkpoint,
    KMarker,
    SwitchbackError,
    GradeAccessError,
    NoAutoResumeError,
    AntiRetryLoopError,
    BudgetExhaustedError,
    LedgerIntegrityError,
    ErrSwitchbackTriggered,
)
from .governor import SwitchbackGovernor
from .ledger import KMarkerLedger, RiskLedger, RightsLedger
from .merkle import MerkleTree, MerkleProof
from .trace import Tracer
from .verifier import LiveEvidenceEngine, SourceSnapshot
from .sidecar import SwitchbackSidecarGateway, SidecarHTTPServer, ConsumerTokenVault
from .mcp_server import SwitchbackMCPServer
from .agentteams import AgentTeamsCluster, MatrixRoomBus, AGENTTEAMS_ROSTER
from .cockpit import build_cockpit_overview, render_cockpit_html, format_im_card
