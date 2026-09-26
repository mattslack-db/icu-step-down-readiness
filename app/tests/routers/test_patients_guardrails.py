"""
Unit tests verifying that inject_risk guardrail flags are surfaced as risk
factors in the patient detail route.

Tests cover:
- active_bleeding flag → injects "active bleeding / coagulopathy" risk factor
- recent_extubation flag → injects "recently extubated (<24h)" risk factor
- Injected factor appears EXACTLY ONCE (dedup guard)
- Injected factor direction is always "risk"
- Neither flag set → no extra factors injected
- Both flags set → both factors injected (each exactly once)

Pattern: call get_patient() directly with mock session and workspace client,
monkey-patching build_narrative, matching test_patients_care_plan.py.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import icu_step_down.backend.routers.patients as patients_mod
from icu_step_down.backend.routers.patients import get_patient
from icu_step_down.backend.routers.census import FEATURE_COLS

# ---------------------------------------------------------------------------
# Stub builders (adapted from test_patients_care_plan.py)
# ---------------------------------------------------------------------------


def _make_session(census_row: dict | None, vitals_rows: list | None = None) -> MagicMock:
    """Return a mock session that serves census_row for all three SQL queries."""
    session = MagicMock()

    def _execute(query, params=None):
        result = MagicMock()
        sql_text = str(query)

        if "census_vitals" in sql_text:
            result.fetchall.return_value = vitals_rows or []
            return result

        if params is None:
            if census_row is not None:
                result.keys.return_value = list(census_row.keys())
                result.fetchall.return_value = [
                    tuple(census_row[k] for k in census_row)
                ]
            else:
                result.keys.return_value = []
                result.fetchall.return_value = []
            return result

        if census_row is not None:
            result.keys.return_value = list(census_row.keys())
            result.fetchone.return_value = tuple(census_row[k] for k in census_row)
        else:
            result.fetchone.return_value = None
        return result

    session.execute.side_effect = _execute
    return session


def _make_ws(score: float = 0.55, factors: list | None = None) -> MagicMock:
    """Return a mock WorkspaceClient whose serving endpoint returns a fixed score."""
    ws = MagicMock()
    ws.config.client_id = None
    if factors is None:
        factors = [{"name": "lactate_last", "direction": "risk", "magnitude": 0.26}]
    ws.serving_endpoints.query.return_value.predictions = [
        {"prediction": json.dumps({"readiness_score": score, "factors": factors})}
    ]
    return ws


def _census_row(icustay_id: str = "999001", **flag_overrides) -> dict:
    """Build a minimal census row; override boolean flags via kwargs."""
    row: dict = {
        "icustay_id": icustay_id,
        "subject_id": "88888",
        "los": 4.0,
        "age": 72.0,
        "on_vasopressors": False,
        "on_ventilator": False,
        "recent_extubation": False,
        "active_bleeding": False,
        "hr_mean": 78.0,
        "sbp_mean": 118.0,
        "dbp_mean": 74.0,
        "spo2_mean": 96.0,
        "spo2_min": 92.0,
        "temp_c_mean": 37.1,
        "rr_mean": 18.0,
        "gcs_last": 14.0,
        "lactate_last": 2.1,
    }
    for col in FEATURE_COLS:
        if col not in row:
            row[col] = None
    row.update(flag_overrides)
    return row


def _call_patient(icustay_id: str, census_row: dict, ws: MagicMock):
    """Call get_patient with stubs and a no-op narrative."""
    session = _make_session(census_row)
    original_build = patients_mod.build_narrative

    def stub_narrative(*args, **kwargs):
        return "Stub narrative."

    patients_mod.build_narrative = stub_narrative
    try:
        return get_patient(icustay_id, session, ws)
    finally:
        patients_mod.build_narrative = original_build


# ---------------------------------------------------------------------------
# Tests: active_bleeding flag
# ---------------------------------------------------------------------------


def test_active_bleeding_flag_injects_single_risk_factor():
    """
    When active_bleeding=True the patient's factor list must contain exactly
    one "active bleeding / coagulopathy" entry with direction "risk".
    """
    # Arrange
    row = _census_row("999001", active_bleeding=True)
    ws = _make_ws(score=0.45)

    # Act
    detail = _call_patient("999001", row, ws)

    # Assert
    labels = [f.name for f in detail.factors]
    assert labels.count("active bleeding / coagulopathy") == 1
    assert all(
        f.direction == "risk"
        for f in detail.factors
        if "bleeding" in f.name
    )


def test_active_bleeding_injected_factor_dedup():
    """
    If the model already returns a factor whose name matches the guardrail
    label, the injection must not duplicate it.
    """
    # Arrange: model factor matches the guardrail label exactly
    duplicate_factor = {
        "name": "active bleeding / coagulopathy",
        "direction": "risk",
        "magnitude": 0.35,
    }
    row = _census_row("999001", active_bleeding=True)
    ws = _make_ws(score=0.45, factors=[duplicate_factor])

    # Act
    detail = _call_patient("999001", row, ws)

    # Assert: still exactly one, not two
    labels = [f.name for f in detail.factors]
    assert labels.count("active bleeding / coagulopathy") == 1


def test_active_bleeding_false_does_not_inject():
    """When active_bleeding=False no bleeding factor is injected."""
    row = _census_row("999001", active_bleeding=False)
    ws = _make_ws(score=0.55)

    detail = _call_patient("999001", row, ws)

    labels = [f.name for f in detail.factors]
    assert "active bleeding / coagulopathy" not in labels


# ---------------------------------------------------------------------------
# Tests: recent_extubation flag
# ---------------------------------------------------------------------------


def test_recent_extubation_flag_injects_single_risk_factor():
    """
    When recent_extubation=True the patient's factor list must contain
    exactly one "recently extubated (<24h)" entry with direction "risk".
    """
    # Arrange
    row = _census_row("999002", recent_extubation=True)
    ws = _make_ws(score=0.50)

    # Act
    detail = _call_patient("999002", row, ws)

    # Assert
    labels = [f.name for f in detail.factors]
    assert labels.count("recently extubated (<24h)") == 1
    assert all(
        f.direction == "risk"
        for f in detail.factors
        if "extubat" in f.name
    )


def test_recent_extubation_false_does_not_inject():
    """When recent_extubation=False no extubation factor is injected."""
    row = _census_row("999002", recent_extubation=False)
    ws = _make_ws(score=0.55)

    detail = _call_patient("999002", row, ws)

    labels = [f.name for f in detail.factors]
    assert "recently extubated (<24h)" not in labels


# ---------------------------------------------------------------------------
# Tests: both flags set simultaneously
# ---------------------------------------------------------------------------


def test_both_flags_inject_both_factors_each_exactly_once():
    """When both flags are set, both guardrail factors appear exactly once."""
    row = _census_row("999003", active_bleeding=True, recent_extubation=True)
    ws = _make_ws(score=0.40)

    detail = _call_patient("999003", row, ws)

    labels = [f.name for f in detail.factors]
    assert labels.count("active bleeding / coagulopathy") == 1
    assert labels.count("recently extubated (<24h)") == 1


# ---------------------------------------------------------------------------
# Tests: injected factor magnitude and ordering
# ---------------------------------------------------------------------------


def test_injected_factor_magnitude_exceeds_existing_factors():
    """
    Injected risk factors must carry a magnitude > all existing factors so
    they sort to the top of the factor list.
    """
    row = _census_row("999001", active_bleeding=True)
    ws = _make_ws(score=0.45, factors=[
        {"name": "lactate_last", "direction": "risk", "magnitude": 0.26},
        {"name": "gcs_last", "direction": "supports", "magnitude": 0.15},
    ])

    detail = _call_patient("999001", row, ws)

    injected = next(
        f for f in detail.factors if f.name == "active bleeding / coagulopathy"
    )
    max_model_magnitude = max(
        f.magnitude for f in detail.factors
        if f.name != "active bleeding / coagulopathy"
    )
    assert injected.magnitude > max_model_magnitude


# ---------------------------------------------------------------------------
# Tests: top-N truncation (I2)
# ---------------------------------------------------------------------------


def test_top_n_truncation_with_inject_risk_flag():
    """
    When 5 model factors are returned AND an inject_risk flag is set,
    the response must contain exactly TOP_N_DISPLAY_FACTORS (5) factors,
    the injected guardrail factor must be present (it has max+epsilon
    magnitude so it sorts first and a low-magnitude model factor is dropped),
    and all 5 must have direction "risk" or "supports" (no phantom entries).
    """
    from icu_step_down.backend.routers.patients import TOP_N_DISPLAY_FACTORS

    # Arrange: 5 model factors with distinct magnitudes
    model_factors = [
        {"name": f"feature_{i}", "direction": "risk", "magnitude": float(i) * 0.05}
        for i in range(1, 6)
    ]  # magnitudes: 0.05, 0.10, 0.15, 0.20, 0.25
    row = _census_row("999004", active_bleeding=True)
    ws = _make_ws(score=0.48, factors=model_factors)

    # Act
    detail = _call_patient("999004", row, ws)

    # Assert: exactly TOP_N_DISPLAY_FACTORS entries
    assert len(detail.factors) == TOP_N_DISPLAY_FACTORS

    # Injected guardrail factor is present (sorted to top)
    labels = [f.name for f in detail.factors]
    assert "active bleeding / coagulopathy" in labels

    # The lowest-magnitude model factor (feature_1, magnitude 0.05) was dropped
    assert "feature_1" not in labels

    # All entries have valid directions
    assert all(f.direction in ("risk", "supports") for f in detail.factors)


# ---------------------------------------------------------------------------
# Tests: M1 — injected risk labels reach build_narrative (M1 regression guard)
# ---------------------------------------------------------------------------


def test_injected_risk_factors_passed_to_build_narrative():
    """
    M1: When an inject_risk flag is set, the factors argument passed to
    build_narrative must include the injected guardrail label.

    Verifies that the narrative's factor list reflects the final displayed
    factors (post-injection), not the raw pre-injection model output.
    """
    # Arrange: one model factor + active_bleeding flag set
    row = _census_row("999005", active_bleeding=True)
    ws = _make_ws(score=0.45, factors=[
        {"name": "lactate_last", "direction": "risk", "magnitude": 0.26},
    ])

    captured_factors: list = []

    def capture_narrative(score, factors, **kwargs):
        captured_factors.extend(factors)
        return "Stub narrative."

    original_build = patients_mod.build_narrative
    patients_mod.build_narrative = capture_narrative
    try:
        session = _make_session(row)
        get_patient("999005", session, ws)
    finally:
        patients_mod.build_narrative = original_build

    # Assert: injected guardrail label is present in captured factors
    factor_names = [f.name for f in captured_factors]
    assert "active bleeding / coagulopathy" in factor_names, (
        f"Expected 'active bleeding / coagulopathy' in narrative factors, got: {factor_names}"
    )


# ---------------------------------------------------------------------------
# Tests: M3 — unconditional TOP_N truncation (no-inject path)
# ---------------------------------------------------------------------------


def test_top_n_truncation_without_inject_risk_flag():
    """
    M3: Even when no guardrail fires, response_factors must be capped at
    TOP_N_DISPLAY_FACTORS.  Ensures the truncation is applied unconditionally.
    """
    from icu_step_down.backend.routers.patients import TOP_N_DISPLAY_FACTORS

    # Arrange: 7 model factors, no flags set
    model_factors = [
        {"name": f"feature_{i}", "direction": "risk", "magnitude": float(i) * 0.05}
        for i in range(1, 8)
    ]
    row = _census_row("999006", active_bleeding=False, recent_extubation=False)
    ws = _make_ws(score=0.55, factors=model_factors)

    # Act
    detail = _call_patient("999006", row, ws)

    # Assert: capped regardless of injection path
    assert len(detail.factors) == TOP_N_DISPLAY_FACTORS
