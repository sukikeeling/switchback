"""Switchback Governance (折返治理).

The human-in-the-loop governance layer for multi-agent teams.

Modeled on the "Ren-shaped" (人字形) switchback line at Qinglongqiao on the
Centennial Jingzhang Railway: a train climbing a steep grade must stop at a
switchback node, change direction, and continue only after a three-party review
decides *pass / turn back / pull into depot*. No scenario continues automatically.

Four mechanisms:
  1. Switchback Node   — fixed checkpoints where any party's veto forces a turn-back.
  2. Grade-based Access — tasks graded gentle/medium/steep; steeper grades face
                          stricter admission review.
  3. K-marker Versioning — every data update / recalc / release records a new
                           kilometer-marker version in an immutable hash chain.
  4. Switch States      — mainline / siding turn-back / depot maintenance, with
                          **no automatic recovery**.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = [
    "__version__",
    "Grade",
    "SwitchState",
    "Verdict",
    "PartyRole",
    "CheckpointKind",
    "SwitchbackError",
    "GradeAccessError",
    "NoAutoResumeError",
    "LedgerIntegrityError",
]

from .protocol import (
    Grade,
    SwitchState,
    Verdict,
    PartyRole,
    CheckpointKind,
    SwitchbackError,
    GradeAccessError,
    NoAutoResumeError,
    LedgerIntegrityError,
)
