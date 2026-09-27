"""
Feature label mapping and clinical direction correction for the ICU Step-Down model.

The model returns raw column names (e.g. ``spo2_min``, ``on_vasopressors``).
This module maps them to human-readable clinical labels and enforces clinically
correct SHAP direction for known binary risk features.
"""

from __future__ import annotations

from .guardrails import GUARDRAILS, apply_direction_override  # noqa: F401 (re-exported)

# ---------------------------------------------------------------------------
# Human-readable clinical labels for all 30 model feature columns.
# ---------------------------------------------------------------------------

FEATURE_LABELS: dict[str, str] = {
    "hr_mean": "mean heart rate",
    "hr_min": "minimum heart rate",
    "hr_max": "maximum heart rate",
    "hr_last": "last heart rate",
    "sbp_mean": "mean systolic BP",
    "sbp_min": "minimum systolic BP",
    "sbp_max": "maximum systolic BP",
    "sbp_last": "last systolic BP",
    "dbp_mean": "mean diastolic BP",
    "dbp_min": "minimum diastolic BP",
    "dbp_max": "maximum diastolic BP",
    "dbp_last": "last diastolic BP",
    "spo2_mean": "mean SpO₂",
    "spo2_min": "minimum SpO₂",
    "spo2_max": "maximum SpO₂",
    "spo2_last": "last SpO₂",
    "temp_c_mean": "mean temperature (°C)",
    "temp_c_min": "minimum temperature (°C)",
    "temp_c_max": "maximum temperature (°C)",
    "temp_c_last": "last temperature (°C)",
    "rr_mean": "mean respiratory rate",
    "rr_min": "minimum respiratory rate",
    "rr_max": "maximum respiratory rate",
    "rr_last": "last respiratory rate",
    "on_vasopressors": "on vasopressors",
    "on_ventilator": "on ventilator",
    "gcs_last": "GCS (last)",
    "lactate_last": "last lactate",
    "los": "ICU length of stay (days)",
    "age": "age (years)",
}

# ---------------------------------------------------------------------------
# Features where the clinical direction is always RISK, regardless of SHAP sign.
#
# Derived from the GUARDRAILS registry (override_risk kind) — kept as a
# frozenset alias for back-compatibility with code that imports it directly.
# ---------------------------------------------------------------------------

ALWAYS_RISK_FEATURES: frozenset[str] = frozenset(
    g.feature for g in GUARDRAILS if g.kind == "override_risk"
)


def normalize_factor(
    raw_name: str,
    direction: str,
    magnitude: float,
) -> tuple[str, str, float]:
    """
    Map a raw model feature name to a human-readable label and enforce
    clinically correct direction.

    Direction is delegated to ``apply_direction_override`` from the declarative
    guardrail registry so that new override rules require only a registry entry,
    not a code change here.

    Args:
        raw_name:  Raw feature column name (e.g. ``"on_vasopressors"``).
        direction: SHAP-derived direction (``"supports"`` | ``"risk"``).
        magnitude: Absolute SHAP value.

    Returns:
        Tuple of (human_label, corrected_direction, magnitude).
    """
    label = FEATURE_LABELS.get(raw_name, raw_name.replace("_", " "))
    direction = apply_direction_override(raw_name, direction)
    return label, direction, magnitude
