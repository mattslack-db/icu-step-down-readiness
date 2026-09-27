"""
Unit tests verifying the patient detail route returns a care_plan field.

Adaptation note: this project has no `client_with_stub_db` pytest fixture.
Tests call the route handler directly with mock session and workspace client
objects — matching the pattern established in test_analytics_router.py.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from icu_step_down.backend.routers.patients import get_patient
from icu_step_down.backend.routers.census import FEATURE_COLS


# ---------------------------------------------------------------------------
# Stub builders
# ---------------------------------------------------------------------------


def _make_session(
    census_row: dict | None, vitals_rows: list | None = None
) -> MagicMock:
    """
    Return a mock session that:
    - For the single-patient lookup (first execute): returns census_row.
    - For the vitals query (second execute): returns vitals_rows.
    - For the batch census query (third execute): returns [census_row].
    """
    session = MagicMock()

    def _execute(query, params=None):
        result = MagicMock()
        sql_text = str(query)

        # Vitals query
        if "census_vitals" in sql_text:
            result.fetchall.return_value = vitals_rows or []
            return result

        # Single patient detail lookup (has the icustay_id predicate)
        if 'icustay_id" = :icustay_id' in sql_text:
            if census_row is not None:
                result.keys.return_value = list(census_row.keys())
                result.fetchone.return_value = tuple(census_row[k] for k in census_row)
            else:
                result.fetchone.return_value = None
            return result

        # Batch census query (no icustay_id predicate)
        if census_row is not None:
            result.keys.return_value = list(census_row.keys())
            result.fetchall.return_value = [tuple(census_row[k] for k in census_row)]
        else:
            result.keys.return_value = []
            result.fetchall.return_value = []
        return result

    session.execute.side_effect = _execute
    return session


def _make_ws(score: float = 0.75) -> MagicMock:
    """Return a mock WorkspaceClient whose serving endpoint returns a fixed score."""
    ws = MagicMock()
    ws.config.client_id = None
    factor = {"name": "lactate_last", "direction": "risk", "magnitude": 0.26}
    ws.serving_endpoints.query.return_value.predictions = [
        {"prediction": json.dumps({"readiness_score": score, "factors": [factor]})}
    ]
    return ws


def _census_row(icustay_id: str = "224403") -> dict:
    """Build a minimal census row with all required columns."""
    row: dict = {
        "icustay_id": icustay_id,
        "subject_id": "99999",
        "los": 3.0,
        "age": 65.0,
        "on_vasopressors": False,
        "on_ventilator": False,
        "hr_mean": 80.0,
        "sbp_mean": 120.0,
        "dbp_mean": 78.0,
        "spo2_mean": 97.0,
        "spo2_min": 94.0,
        "temp_c_mean": 37.0,
        "rr_mean": 16.0,
        "gcs_last": 15.0,
        "lactate_last": 1.8,
    }
    for col in FEATURE_COLS:
        if col not in row:
            row[col] = None
    return row


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_patient_detail_includes_care_plan():
    """GET /api/patients/{icustay_id} response includes a care_plan object."""
    row = _census_row("224403")
    session = _make_session(row)
    ws = _make_ws(score=0.75)

    # Stub the narrative so we don't hit Databricks
    import icu_step_down.backend.routers.patients as patients_mod

    original_build = patients_mod.build_narrative

    def stub_narrative(*args, **kwargs):
        return "Borderline. Recheck lactate."

    patients_mod.build_narrative = stub_narrative
    try:
        detail = get_patient("224403", session, ws, None)
    finally:
        patients_mod.build_narrative = original_build

    assert hasattr(detail, "care_plan"), "PatientDetail must have a care_plan field"
    assert detail.care_plan is not None
    assert detail.care_plan.next_check_in_hours in (4, 6, 12)
    assert isinstance(detail.care_plan.monitoring, list)
    assert len(detail.care_plan.monitoring) > 0
