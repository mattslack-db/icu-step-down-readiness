"""
Feature label mapping and clinical direction correction for the ICU Step-Down model.

The model returns raw column names (e.g. ``spo2_min``, ``on_vasopressors``).
This module maps them to human-readable clinical labels and enforces clinically
correct SHAP direction for known binary risk features.
"""

from __future__ import annotations

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
# Being on vasopressors or a ventilator indicates haemodynamic/respiratory
# instability and never supports step-down readiness.  When the SHAP value
# is positive for these features (e.g. because the model learned a correlation
# artefact) we override the direction to "risk" to avoid misleading clinicians.
# ---------------------------------------------------------------------------

ALWAYS_RISK_FEATURES: frozenset[str] = frozenset(
    {"on_vasopressors", "on_ventilator"}
)


def normalize_factor(
    raw_name: str,
    direction: str,
    magnitude: float,
) -> tuple[str, str, float]:
    """
    Map a raw model feature name to a human-readable label and enforce
    clinically correct direction.

    Args:
        raw_name:  Raw feature column name (e.g. ``"on_vasopressors"``).
        direction: SHAP-derived direction (``"supports"`` | ``"risk"``).
        magnitude: Absolute SHAP value.

    Returns:
        Tuple of (human_label, corrected_direction, magnitude).
    """
    label = FEATURE_LABELS.get(raw_name, raw_name.replace("_", " "))
    if raw_name in ALWAYS_RISK_FEATURES:
        direction = "risk"
    return label, direction, magnitude
