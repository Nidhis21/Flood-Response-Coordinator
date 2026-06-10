"""
utils.py — Core mathematical functions used by agents.

Contains:
  1. haversine()        — great-circle distance between two GPS points
  2. rational_model()   — FLEWS paper rational method for peak discharge
  3. priority_score()   — priority auction formula for conflict resolution
"""

import math


# ---------------------------------------------------------------------------
# 1. HAVERSINE DISTANCE
# ---------------------------------------------------------------------------
def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth.

    Args:
        lat1, lng1: Latitude and longitude of point 1 (decimal degrees)
        lat2, lng2: Latitude and longitude of point 2 (decimal degrees)

    Returns:
        Distance in kilometres.

    Use: Finding the nearest available resource to an SOS location.
    """
    R = 6371.0  # Earth's mean radius in km

    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# ---------------------------------------------------------------------------
# 2. RATIONAL MODEL (FLEWS Paper — peak discharge estimation)
# ---------------------------------------------------------------------------
def rational_model(C: float, I: float, A: float) -> float:
    """
    Compute peak discharge using the Rational Method from the FLEWS paper.

    Formula:  Q = 0.0028 × C × I × A

    Args:
        C: Runoff coefficient (0–1), depends on soil type and land cover.
           Example: 0.233 for Lakhimpur alluvial soil.
        I: Rainfall intensity in mm/hr.
           Example: 42.5 mm/hr during 2012 Lakhimpur flood.
        A: Watershed area in hectares.
           Example: 134600 ha for Ranganadi basin.

    Returns:
        Q — Peak discharge in cumecs (m³/s).

    Use: Prediction Agent computes flood risk per river basin.
    """
    return 0.0028 * C * I * A


# ---------------------------------------------------------------------------
# 3. PRIORITY AUCTION FORMULA (Project Differentiator)
# ---------------------------------------------------------------------------
def priority_score(
    lives: float,
    time_to_critical: float,
    irreversibility: float,
    distance_cost: float,
    alpha: float = 0.4,
    beta: float = 0.3,
    gamma: float = 0.2,
    delta: float = 0.1,
) -> float:
    """
    Compute a priority score for the conflict resolution auction.

    Formula:
        Score = α(Lives at Risk) + β(1/Time to Critical) + γ(Irreversibility) − δ(Distance Cost)

    All inputs MUST be normalized to 0–1 before calling this function.

    Args:
        lives:             Normalized lives at risk (0–1). Higher = more lives.
        time_to_critical:  Normalized time until situation becomes critical (0–1).
                           Lower value = more urgent, so formula uses 1/value.
        irreversibility:   Normalized irreversibility (0–1). Higher = harder to undo.
        distance_cost:     Normalized distance/cost (0–1). Higher = farther away.
        alpha, beta, gamma, delta: Tunable weights (default 0.4, 0.3, 0.2, 0.1).

    Returns:
        Priority score (float). Higher score = higher priority for the resource.

    Use: Conflict Resolution Agent decides which SOS gets the contested resource.
    """
    # Guard against division by zero — if time_to_critical is 0, treat as max urgency
    urgency = (1.0 / time_to_critical) if time_to_critical > 0 else 1.0
    # Clamp urgency to [0, 1] after inversion
    urgency = min(urgency, 1.0)

    return alpha * lives + beta * urgency + gamma * irreversibility - delta * distance_cost
