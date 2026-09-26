"""
Unit tests for src.monitoring.baseline — pure helper functions.

Tests cover parse_scores (JSON-prediction parser) and compute_decile_quantiles
(scores_to_quantiles).  Neither touches Spark, Databricks, or the live model.

Run from repo root:
    pytest tests/monitoring/test_baseline.py -v
"""

from __future__ import annotations

import json

import pytest

from src.monitoring.baseline import compute_decile_quantiles, parse_scores


# ---------------------------------------------------------------------------
# parse_scores
# ---------------------------------------------------------------------------


class TestParseScores:
    def test_extracts_readiness_score_from_single_prediction(self) -> None:
        """parse_scores returns the readiness_score float from a JSON string."""
        predictions = [json.dumps({"readiness_score": 0.75, "factors": []})]
        assert parse_scores(predictions) == pytest.approx([0.75])

    def test_extracts_multiple_scores_in_order(self) -> None:
        """parse_scores preserves order across multiple predictions."""
        raw = [0.10, 0.55, 0.90, 0.30]
        predictions = [
            json.dumps({"readiness_score": s, "factors": []}) for s in raw
        ]
        assert parse_scores(predictions) == pytest.approx(raw)

    def test_handles_empty_list(self) -> None:
        """parse_scores returns an empty list for empty input."""
        assert parse_scores([]) == []

    def test_ignores_factors_field(self) -> None:
        """parse_scores is not affected by the factors payload."""
        factors = [{"name": "lactate_last", "direction": "risk", "magnitude": 0.2}]
        prediction = json.dumps({"readiness_score": 0.42, "factors": factors})
        result = parse_scores([prediction])
        assert result == pytest.approx([0.42])

    def test_does_not_mutate_input_list(self) -> None:
        """parse_scores must not modify the input list (immutability)."""
        predictions = [json.dumps({"readiness_score": 0.5, "factors": []})]
        original = list(predictions)
        parse_scores(predictions)
        assert predictions == original

    def test_scores_are_floats(self) -> None:
        """parse_scores always returns float values."""
        predictions = [json.dumps({"readiness_score": 1, "factors": []})]
        result = parse_scores(predictions)
        assert all(isinstance(s, float) for s in result)


# ---------------------------------------------------------------------------
# compute_decile_quantiles  (scores_to_quantiles)
# ---------------------------------------------------------------------------


class TestComputeDecileQuantiles:
    def test_returns_eleven_pairs(self) -> None:
        """Returns exactly 11 (quantile, score) pairs (0.0 through 1.0)."""
        scores = [float(i) / 10.0 for i in range(11)]
        result = compute_decile_quantiles(scores)
        assert len(result) == 11

    def test_quantile_values_are_0_to_1_in_steps(self) -> None:
        """Quantile component increments by 0.1 from 0.0 to 1.0."""
        scores = [float(i) for i in range(100)]
        result = compute_decile_quantiles(scores)
        expected_qs = [round(i / 10, 1) for i in range(11)]
        actual_qs = [q for q, _ in result]
        assert actual_qs == pytest.approx(expected_qs)

    def test_first_quantile_is_min_score(self) -> None:
        """The 0.0 quantile equals the minimum score."""
        scores = [0.1, 0.5, 0.9, 0.3, 0.7]
        result = compute_decile_quantiles(scores)
        q0, s0 = result[0]
        assert q0 == pytest.approx(0.0)
        assert s0 == pytest.approx(min(scores))

    def test_last_quantile_is_max_score(self) -> None:
        """The 1.0 quantile equals the maximum score."""
        scores = [0.1, 0.5, 0.9, 0.3, 0.7]
        result = compute_decile_quantiles(scores)
        q10, s10 = result[-1]
        assert q10 == pytest.approx(1.0)
        assert s10 == pytest.approx(max(scores))

    def test_scores_are_non_decreasing(self) -> None:
        """Score values in quantile output must be non-decreasing."""
        scores = [0.9, 0.1, 0.5, 0.3, 0.7, 0.2, 0.8, 0.4, 0.6, 0.0, 1.0]
        result = compute_decile_quantiles(scores)
        vals = [s for _, s in result]
        assert vals == sorted(vals)

    def test_identical_scores_produce_identical_quantile_values(self) -> None:
        """All-identical scores → all quantile scores equal that value."""
        scores = [0.5] * 20
        result = compute_decile_quantiles(scores)
        for _, s in result:
            assert s == pytest.approx(0.5)

    def test_does_not_mutate_input(self) -> None:
        """compute_decile_quantiles must not mutate the input list."""
        scores = [0.5, 0.1, 0.9, 0.3, 0.7]
        original = list(scores)
        compute_decile_quantiles(scores)
        assert scores == original

    def test_raises_on_empty_input(self) -> None:
        """Raises ValueError for an empty score list."""
        with pytest.raises(ValueError, match="[Ee]mpty|empty"):
            compute_decile_quantiles([])

    def test_single_score_returns_same_value_for_all_quantiles(self) -> None:
        """A single score produces a single distinct quantile score value."""
        result = compute_decile_quantiles([0.77])
        for _, s in result:
            assert s == pytest.approx(0.77)
