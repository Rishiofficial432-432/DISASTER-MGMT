"""
Step 4: Relocation priority engine — rule-based scoring.

Combines:
  - hazard exposure (from point_in_polygon.py: hazard_type, severity, overlap_fraction)
  - overcrowding (from capacity/thresholds.py: density tier)
into a single priority rank per settlement.

Keep this rule-based and explainable (SIH judges will want to see the logic,
not a black box) — simple weighted score is fine for MVP.
"""

from __future__ import annotations  # allows `str | None` syntax on Python 3.9+

from dataclasses import dataclass
from app.capacity.thresholds import classify_density


SEVERITY_WEIGHTS = {"low": 1, "moderate": 2, "high": 3, "extreme": 4}
DENSITY_TIER_WEIGHTS = {"low": 1, "moderate": 2, "high": 3}


@dataclass
class SettlementAssessment:
    settlement_id: str
    hazard_type: str | None
    hazard_severity: str | None
    overlap_fraction: float
    persons_per_hectare: float
    terrain: str = "plain"
    density_tier: str = ""
    priority_score: float = 0.0
    priority_rank: str = ""

    def __post_init__(self):
        # Derive density_tier from real URDPFI thresholds instead of requiring
        # the caller to classify it manually.
        self.density_tier = classify_density(self.persons_per_hectare, self.terrain)


def score_settlement(hazard_severity: str | None, overlap_fraction: float, density_tier: str) -> float:
    """
    Simple weighted score:
      score = (hazard_severity_weight * overlap_fraction) + density_tier_weight
    Tune weights once real data is available.
    """
    hazard_component = SEVERITY_WEIGHTS.get(hazard_severity, 0) * overlap_fraction
    density_component = DENSITY_TIER_WEIGHTS.get(density_tier, 0)
    return round(hazard_component + density_component, 2)


def rank_settlements(assessments: list[SettlementAssessment]) -> list[SettlementAssessment]:
    """Score and sort settlements by priority, highest first."""
    for a in assessments:
        a.priority_score = score_settlement(a.hazard_severity, a.overlap_fraction, a.density_tier)
    assessments.sort(key=lambda a: a.priority_score, reverse=True)

    # Simple tiering — top third = high, middle third = medium, rest = low
    n = len(assessments)
    for i, a in enumerate(assessments):
        if i < n / 3:
            a.priority_rank = "high"
        elif i < 2 * n / 3:
            a.priority_rank = "medium"
        else:
            a.priority_rank = "low"
    return assessments
