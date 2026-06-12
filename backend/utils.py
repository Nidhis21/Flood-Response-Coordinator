"""
utils.py — Core mathematical functions used by agents.

Contains:
  1. haversine()            — great-circle distance between two GPS points
  2. rational_model()       — FLEWS paper rational method for peak discharge
  3. priority_score()       — low-level priority auction formula
  4. run_priority_auction() — full auction with normalization, weight profiles, phase adjustment
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
# 3. PRIORITY SCORE (low-level formula)
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

    Returns:
        Priority score (float). Higher score = higher priority for the resource.
    """
    # Guard against division by zero — if time_to_critical is 0, treat as max urgency
    urgency = (1.0 / time_to_critical) if time_to_critical > 0 else 1.0
    # Clamp urgency to [0, 1] after inversion
    urgency = min(urgency, 1.0)

    return alpha * lives + beta * urgency + gamma * irreversibility - delta * distance_cost


# ---------------------------------------------------------------------------
# 4. WEIGHT PROFILES — AHP-derived for each conflict type (Saaty, 1980)
# ---------------------------------------------------------------------------
WEIGHT_PROFILES = {
    "rescue_vs_rescue":     {"alpha": 0.45, "beta": 0.35, "gamma": 0.15, "delta": 0.05},
    "medical_vs_medical":   {"alpha": 0.30, "beta": 0.25, "gamma": 0.35, "delta": 0.10},
    "logistics_vs_logistics": {"alpha": 0.30, "beta": 0.20, "gamma": 0.20, "delta": 0.30},
    "rescue_vs_medical":    {"alpha": 0.35, "beta": 0.30, "gamma": 0.25, "delta": 0.10},
    "rescue_vs_logistics":  {"alpha": 0.50, "beta": 0.30, "gamma": 0.15, "delta": 0.05},
    "medical_vs_logistics": {"alpha": 0.40, "beta": 0.25, "gamma": 0.25, "delta": 0.10},
}

PHASE_MULTIPLIERS = {
    "early":    {"alpha": 1.0, "beta": 0.8, "gamma": 1.0, "delta": 1.2},
    "peak":     {"alpha": 1.2, "beta": 1.2, "gamma": 1.0, "delta": 0.7},
    "receding": {"alpha": 0.9, "beta": 1.0, "gamma": 1.2, "delta": 1.0},
}

# Irreversibility reference values from prompt
IRREVERSIBILITY_REF = {
    "drowning":           1.0,
    "structural_collapse": 1.0,
    "severe_injury":      0.8,
    "unconscious":        0.8,
    "epidemic_risk":      0.8,
    "moderate_injury":    0.6,
    "water_shortage":     0.5,
    "food_shortage":      0.4,
    "minor_injury":       0.2,
    "pre_positioning":    0.1,
}


# ---------------------------------------------------------------------------
# 5. NORMALIZE INPUTS — per the Conflict Resolution prompt
# ---------------------------------------------------------------------------
def _normalize_lives(raw_lives: float) -> float:
    """Divide by 10, cap at 1.0. (3 people = 0.30, 10+ = 1.0)"""
    return min(1.0, raw_lives / 10.0)


def _normalize_time(raw_minutes: float) -> float:
    """
    Reciprocal normalized against 5-minute baseline, cap at 1.0.
    5 mins = 1.0, 30 mins = 0.17, 120 mins = 0.04
    """
    if raw_minutes <= 0:
        return 1.0
    return min(1.0, 5.0 / raw_minutes)


def _normalize_distance(raw_km: float) -> float:
    """Divide by 50km max range, cap at 1.0."""
    return min(1.0, raw_km / 50.0)


def _get_conflict_type(type_a: str, type_b: str) -> str:
    """Determine weight profile key from two request types."""
    types = sorted([type_a.lower(), type_b.lower()])
    key = f"{types[0]}_vs_{types[1]}"
    if key in WEIGHT_PROFILES:
        return key
    # Try reverse order
    key_rev = f"{types[1]}_vs_{types[0]}"
    if key_rev in WEIGHT_PROFILES:
        return key_rev
    # Default to rescue_vs_rescue
    return "rescue_vs_rescue"


def _apply_phase_adjustment(weights: dict, phase: str) -> dict:
    """Apply disaster phase multipliers and renormalize to sum to 1.0."""
    multipliers = PHASE_MULTIPLIERS.get(phase, PHASE_MULTIPLIERS["peak"])

    adjusted = {
        "alpha": weights["alpha"] * multipliers.get("alpha", 1.0),
        "beta":  weights["beta"]  * multipliers.get("beta", 1.0),
        "gamma": weights["gamma"] * multipliers.get("gamma", 1.0),
        "delta": weights["delta"] * multipliers.get("delta", 1.0),
    }

    # Renormalize to sum to 1.0
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: round(v / total, 4) for k, v in adjusted.items()}

    return adjusted


# ---------------------------------------------------------------------------
# 6. RUN PRIORITY AUCTION — full pipeline
# ---------------------------------------------------------------------------
def run_priority_auction(
    request_a: dict,
    request_b: dict,
    disaster_phase: str = "peak",
) -> dict:
    """
    Full priority auction pipeline with normalization, weight selection,
    phase adjustment, vulnerable population bonus, and tiebreaking.

    Each request dict should contain:
        - type: str          ("rescue", "medical", "logistics")
        - lives_at_risk: int (raw count, will be normalized)
        - time_to_critical_minutes: float (minutes, default 60)
        - irreversibility: float (0–1, or inferred)
        - distance_km: float (raw km, default 15)
        - vulnerable_population: bool (elderly/children/disabled)
        - sos_id: int (for tiebreaking)
        - people_count: int (for tiebreaking)

    Returns dict with:
        - score_a, score_b, winner ("a" or "b"), conflict_type,
          weights_used, normalized inputs, phase
    """
    # 1. Extract raw values with defaults for missing data
    type_a = request_a.get("type", "rescue")
    type_b = request_b.get("type", "rescue")

    lives_a = float(request_a.get("lives_at_risk", request_a.get("people_count", 1)))
    lives_b = float(request_b.get("lives_at_risk", request_b.get("people_count", 1)))

    time_a = float(request_a.get("time_to_critical_minutes",
                   request_a.get("time_to_critical_hours", 1.0) * 60))
    time_b = float(request_b.get("time_to_critical_minutes",
                   request_b.get("time_to_critical_hours", 1.0) * 60))

    # Default time to 60 minutes if 0 or missing
    if time_a <= 0:
        time_a = 60.0
    if time_b <= 0:
        time_b = 60.0

    irrev_a = float(request_a.get("irreversibility", 0.5))
    irrev_b = float(request_b.get("irreversibility", 0.5))

    dist_a = float(request_a.get("distance_km", 15.0))
    dist_b = float(request_b.get("distance_km", 15.0))

    # 2. Vulnerable population bonus (+0.15 to irreversibility, cap at 1.0)
    vuln_a = request_a.get("vulnerable_population", False)
    vuln_b = request_b.get("vulnerable_population", False)
    if vuln_a:
        irrev_a = min(1.0, irrev_a + 0.15)
    if vuln_b:
        irrev_b = min(1.0, irrev_b + 0.15)

    # 3. Normalize inputs
    norm_lives_a = _normalize_lives(lives_a)
    norm_lives_b = _normalize_lives(lives_b)
    norm_time_a  = _normalize_time(time_a)
    norm_time_b  = _normalize_time(time_b)
    norm_irrev_a = min(1.0, max(0.0, irrev_a))
    norm_irrev_b = min(1.0, max(0.0, irrev_b))
    norm_dist_a  = _normalize_distance(dist_a)
    norm_dist_b  = _normalize_distance(dist_b)

    # 4. Select weight profile
    conflict_type = _get_conflict_type(type_a, type_b)
    base_weights = WEIGHT_PROFILES[conflict_type].copy()

    # 5. Apply disaster phase adjustment
    weights = _apply_phase_adjustment(base_weights, disaster_phase)

    # 6. Compute scores using low-level formula
    # Note: time is already normalized via _normalize_time, so we pass it directly
    # The priority_score function expects normalized inputs and does 1/time internally
    # But we already did the normalization, so pass time as the normalized value
    # and set time_to_critical = 1 so 1/1 = 1 and the beta term uses our normalized time
    score_a = (
        weights["alpha"] * norm_lives_a
        + weights["beta"] * norm_time_a
        + weights["gamma"] * norm_irrev_a
        - weights["delta"] * norm_dist_a
    )
    score_b = (
        weights["alpha"] * norm_lives_b
        + weights["beta"] * norm_time_b
        + weights["gamma"] * norm_irrev_b
        - weights["delta"] * norm_dist_b
    )

    # Clamp to [0, 1]
    score_a = round(min(1.0, max(0.0, score_a)), 3)
    score_b = round(min(1.0, max(0.0, score_b)), 3)

    # 7. Determine winner with tiebreaking
    if abs(score_a - score_b) <= 0.05:
        # Tiebreaker 1: more people at risk
        people_a = int(request_a.get("people_count", request_a.get("lives_at_risk", 1)))
        people_b = int(request_b.get("people_count", request_b.get("lives_at_risk", 1)))
        if people_a > people_b:
            winner = "a"
            tiebreaker = f"tiebreak_people ({people_a} vs {people_b})"
        elif people_b > people_a:
            winner = "b"
            tiebreaker = f"tiebreak_people ({people_b} vs {people_a})"
        else:
            # Tiebreaker 2: earlier SOS (lower ID)
            sos_a = int(request_a.get("sos_id", 9999))
            sos_b = int(request_b.get("sos_id", 9999))
            winner = "a" if sos_a <= sos_b else "b"
            tiebreaker = f"tiebreak_sos_id ({sos_a} vs {sos_b})"
    else:
        winner = "a" if score_a > score_b else "b"
        tiebreaker = None

    return {
        "score_a": score_a,
        "score_b": score_b,
        "winner": winner,
        "conflict_type": conflict_type,
        "disaster_phase": disaster_phase,
        "weights_used": weights,
        "tiebreaker": tiebreaker,
        "normalized": {
            "a": {
                "lives": norm_lives_a, "time": norm_time_a,
                "irreversibility": norm_irrev_a, "distance": norm_dist_a,
                "vulnerable_bonus": vuln_a,
            },
            "b": {
                "lives": norm_lives_b, "time": norm_time_b,
                "irreversibility": norm_irrev_b, "distance": norm_dist_b,
                "vulnerable_bonus": vuln_b,
            },
        },
    }
