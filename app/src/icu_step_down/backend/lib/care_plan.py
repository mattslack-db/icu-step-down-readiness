"""Deterministic care-plan layer: maps band + factors to a concrete
next-check-in interval and monitoring thresholds. The FM narrative renders
these fields into prose — it never invents them."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class MonitoringItem:
    parameter: str
    threshold: str
    rationale: str


@dataclass(frozen=True)
class CarePlan:
    next_check_in_hours: int
    monitoring: tuple[MonitoringItem, ...]
    basis: str


# Band → default reassessment interval (hours). Sicker band = tighter.
_BAND_INTERVAL = {"Ready": 12, "Borderline": 6, "Not ready": 4}

# Raw/label factor name → monitoring rule. Keyed on the normalized label
# substrings the app produces (see feature_labels.FEATURE_LABELS).
_FACTOR_RULES: dict[str, MonitoringItem] = {
    "lactate": MonitoringItem("lactate", "recheck in 6h; escalate if >2.0 mmol/L",
                              "elevated/last lactate is a top driver"),
    "heart rate": MonitoringItem("heart rate", "continuous; escalate if sustained >110 bpm",
                                 "heart-rate instability among top factors"),
    "SpO₂": MonitoringItem("SpO₂", "continuous; escalate if <92%",
                           "oxygenation among top factors"),
    "respiratory rate": MonitoringItem("respiratory rate", "hourly; escalate if >24/min",
                                       "respiratory effort among top factors"),
    "systolic BP": MonitoringItem("systolic BP", "q1h; escalate if <90 mmHg",
                                  "haemodynamics among top factors"),
    "GCS": MonitoringItem("GCS", "q2h neuro checks; escalate if drop ≥2",
                          "neurologic status among top factors"),
}


def build_care_plan(band: str, factors: list[tuple[str, str, float]]) -> CarePlan:
    interval = _BAND_INTERVAL.get(band, 4)
    monitoring: list[MonitoringItem] = []
    for label, _direction, _mag in factors:
        for key, item in _FACTOR_RULES.items():
            if key.lower() in label.lower() and item not in monitoring:
                monitoring.append(item)
    if not monitoring:
        monitoring.append(MonitoringItem(
            "vitals", "reassess full vital set at next check-in",
            "insufficient factor signal — clinician review required"))
        interval = min(interval, 4)
    return CarePlan(next_check_in_hours=interval,
                    monitoring=tuple(monitoring),
                    basis=f"band={band}; {len(factors)} factors considered")
