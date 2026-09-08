"""
Unit tests for the analytics router.

Tests cover the global feature importance list, the analytics SQL
structure, and the band-distribution aggregation in the real
get_analytics route (Lakebase session + serving endpoint mocked).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from icu_step_down.backend.lib.feature_labels import FEATURE_LABELS
from icu_step_down.backend.routers.analytics import _GLOBAL_FEATURE_IMPORTANCE, get_analytics
from icu_step_down.backend.routers.census import FEATURE_COLS


# ---------------------------------------------------------------------------
# Global feature importance
# ---------------------------------------------------------------------------


class TestGlobalFeatureImportance:
    def test_non_empty(self) -> None:
        assert len(_GLOBAL_FEATURE_IMPORTANCE) > 0

    def test_all_importances_positive(self) -> None:
        for name, importance in _GLOBAL_FEATURE_IMPORTANCE:
            assert importance > 0, f"Negative importance for {name}"

    def test_sorted_descending(self) -> None:
        importances = [imp for _, imp in _GLOBAL_FEATURE_IMPORTANCE]
        assert importances == sorted(importances, reverse=True), \
            "Feature importance should be sorted descending"

    def test_all_features_in_feature_labels(self) -> None:
        """All tracked features should have a human-readable label."""
        for name, _ in _GLOBAL_FEATURE_IMPORTANCE:
            assert name in FEATURE_LABELS, (
                f"Feature '{name}' in importance list has no label in FEATURE_LABELS"
            )

    def test_top_feature_is_lactate(self) -> None:
        """Lactate is the dominant feature in the v2 model (importance ~0.246)."""
        top_name, top_val = _GLOBAL_FEATURE_IMPORTANCE[0]
        assert top_name == "lactate_last"
        assert top_val == pytest.approx(0.24580, abs=1e-4)

    def test_at_least_ten_features(self) -> None:
        assert len(_GLOBAL_FEATURE_IMPORTANCE) >= 10

    def test_no_duplicate_feature_names(self) -> None:
        names = [n for n, _ in _GLOBAL_FEATURE_IMPORTANCE]
        assert len(names) == len(set(names)), "Duplicate feature names found"


# ---------------------------------------------------------------------------
# Feature columns alignment
# ---------------------------------------------------------------------------


class TestFeatureColsAlignment:
    def test_on_vasopressors_in_feature_cols(self) -> None:
        assert "on_vasopressors" in FEATURE_COLS

    def test_on_ventilator_in_feature_cols(self) -> None:
        assert "on_ventilator" in FEATURE_COLS

    def test_lactate_last_in_feature_cols(self) -> None:
        assert "lactate_last" in FEATURE_COLS

    def test_expected_column_count(self) -> None:
        # 4 vitals × 6 types (hr, sbp, dbp, spo2, temp_c, rr) + 2 binary + gcs + lactate + los + age = 30
        assert len(FEATURE_COLS) == 30

    def test_all_importance_features_are_in_feature_cols(self) -> None:
        """Every feature tracked in global importance must be in the feature column list."""
        for name, _ in _GLOBAL_FEATURE_IMPORTANCE:
            assert name in FEATURE_COLS, (
                f"Importance feature '{name}' not in FEATURE_COLS"
            )


# ---------------------------------------------------------------------------
# Band distribution via the REAL get_analytics route (mocked Lakebase + serving)
# ---------------------------------------------------------------------------


def _make_session(rows: list[dict]) -> MagicMock:
    """Return a mock SQLModel session that yields the given census rows."""
    session = MagicMock()
    result = MagicMock()
    if rows:
        result.keys.return_value = list(rows[0].keys())
        result.fetchall.return_value = [
            tuple(row[k] for k in rows[0].keys()) for row in rows
        ]
    else:
        result.keys.return_value = []
        result.fetchall.return_value = []
    session.execute.return_value = result
    return session


def _make_ws(scores: list[float]) -> MagicMock:
    """Return a mock WorkspaceClient whose serving endpoint returns the given scores."""
    ws = MagicMock()
    ws.config.client_id = None
    ws.serving_endpoints.query.return_value.predictions = [
        {"prediction": json.dumps({"readiness_score": s, "factors": []})}
        for s in scores
    ]
    return ws


def _census_row(icustay_id: str, los: float = 5.0) -> dict:
    """Build a minimal census row with all FEATURE_COLS present."""
    row: dict = {"icustay_id": icustay_id}
    for col in FEATURE_COLS:
        if col == "los":
            row[col] = los
        elif col in ("on_vasopressors", "on_ventilator"):
            row[col] = 0
        else:
            row[col] = None
    return row


class TestBandDistributionViaRoute:
    """Verify band distribution aggregation in the real get_analytics route."""

    def test_equal_split_across_three_bands(self) -> None:
        """Scores spanning low/mid/high produce a roughly equal band split."""
        rows = [_census_row(f"icu-{i}", los=float(i)) for i in range(6)]
        # Raw scores will be rank-normalised into indices roughly 0, 20, 40, 60, 80, 100
        scores = [0.10, 0.20, 0.30, 0.70, 0.80, 0.90]

        resp = get_analytics(_make_session(rows), _make_ws(scores))

        band_map = {b.band: b.count for b in resp.band_distribution}
        # Ready (index ≥ 66): two highest scores → 2
        # Borderline (33–65): two middle scores → 2
        # Not ready (< 33): two lowest scores → 2
        assert band_map.get("Ready", 0) == 2
        assert band_map.get("Borderline", 0) == 2
        assert band_map.get("Not ready", 0) == 2
        assert sum(b.count for b in resp.band_distribution) == 6

    def test_percentages_sum_to_100(self) -> None:
        """Band percentages must sum to 100 (within rounding tolerance)."""
        rows = [_census_row(f"icu-{i}") for i in range(10)]
        scores = [float(i) / 10.0 for i in range(10)]

        resp = get_analytics(_make_session(rows), _make_ws(scores))

        total_pct = sum(b.pct for b in resp.band_distribution)
        assert total_pct == pytest.approx(100.0, abs=1.0)

    def test_empty_census_returns_empty_distribution(self) -> None:
        """When there are no census rows, the route returns zero counts."""
        session = _make_session([])
        ws = _make_ws([])

        resp = get_analytics(session, ws)

        assert resp.total_census == 0
        assert resp.band_distribution == []
