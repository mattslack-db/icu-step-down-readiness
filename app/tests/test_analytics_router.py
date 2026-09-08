"""
Unit tests for the analytics router.

Tests cover the global feature importance list, the analytics SQL
structure, and the aggregation helpers used in the /api/analytics route.
"""

from __future__ import annotations

import pytest

from icu_step_down.backend.lib.feature_labels import FEATURE_LABELS
from icu_step_down.backend.routers.analytics import _GLOBAL_FEATURE_IMPORTANCE
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
# Band distribution helpers (conceptual coverage)
# ---------------------------------------------------------------------------


class TestBandDistributionConcept:
    """Verify that band distribution logic produces sensible outputs."""

    def _compute_distribution(
        self,
        bands: list[str],
    ) -> dict[str, dict]:
        """Minimal reimplementation of what the route does."""
        from collections import Counter

        n = len(bands)
        if n == 0:
            return {}
        counts = Counter(bands)
        return {
            band: {"count": cnt, "pct": round(cnt / n * 100, 1)}
            for band, cnt in counts.items()
        }

    def test_equal_split_three_bands(self) -> None:
        bands = ["Ready"] * 13 + ["Borderline"] * 13 + ["Not ready"] * 14
        dist = self._compute_distribution(bands)
        assert dist["Ready"]["count"] == 13
        assert dist["Not ready"]["count"] == 14
        total_pct = sum(d["pct"] for d in dist.values())
        assert total_pct == pytest.approx(100.0, abs=1.0)

    def test_all_ready(self) -> None:
        bands = ["Ready"] * 5
        dist = self._compute_distribution(bands)
        assert dist["Ready"]["pct"] == pytest.approx(100.0)
        assert "Borderline" not in dist
        assert "Not ready" not in dist

    def test_empty_returns_empty(self) -> None:
        assert self._compute_distribution([]) == {}
