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

import pandas as pd

from src.monitoring.baseline import (
    _FEATURE_COLS,
    _coerce_feature_frame,
    compute_decile_quantiles,
    parse_scores,
)

# ---------------------------------------------------------------------------
# Guard: _FEATURE_COLS must stay in sync with src.ml.model.FEATURE_COLS
# ---------------------------------------------------------------------------
# src/ml/model.py runs mlflow.models.set_model() and imports mlflow/lgbm/shap
# at module load, so we can't unconditionally import it in every test run.
# Strategy:
#   1. Try to import — if mlflow is available, assert exact list equality.
#   2. If mlflow is absent (importorskip skips gracefully), fall back to a
#      structural guard: length == 30 and the known tail matches exactly.
# ---------------------------------------------------------------------------


_KNOWN_TAIL = [
    "on_vasopressors", "on_ventilator",
    "gcs_last", "lactate_last", "los", "age",
]
_KNOWN_HEAD = ["hr_mean", "hr_min", "hr_max", "hr_last"]


class TestFeatureColsGuard:
    def test_feature_cols_length_is_30(self) -> None:
        """_FEATURE_COLS must have exactly 30 entries (matching FEATURE_COLS in model.py)."""
        assert len(_FEATURE_COLS) == 30, (
            f"_FEATURE_COLS has {len(_FEATURE_COLS)} entries; expected 30. "
            "Update baseline._FEATURE_COLS to match src/ml/model.py:FEATURE_COLS."
        )

    def test_feature_cols_head_matches_model(self) -> None:
        """First four entries must be the heart-rate stats (hr_mean/min/max/last)."""
        assert list(_FEATURE_COLS[:4]) == _KNOWN_HEAD, (
            f"Head mismatch: {_FEATURE_COLS[:4]!r} != {_KNOWN_HEAD!r}. "
            "Keep baseline._FEATURE_COLS in sync with src/ml/model.py:FEATURE_COLS."
        )

    def test_feature_cols_tail_matches_model(self) -> None:
        """Last six entries must match the known tail of FEATURE_COLS."""
        assert list(_FEATURE_COLS[-6:]) == _KNOWN_TAIL, (
            f"Tail mismatch: {_FEATURE_COLS[-6:]!r} != {_KNOWN_TAIL!r}. "
            "Keep baseline._FEATURE_COLS in sync with src/ml/model.py:FEATURE_COLS."
        )

    def test_feature_cols_no_duplicates(self) -> None:
        """_FEATURE_COLS must not contain duplicate column names."""
        assert len(_FEATURE_COLS) == len(set(_FEATURE_COLS)), (
            "Duplicate entries found in baseline._FEATURE_COLS."
        )

    def test_feature_cols_exact_equality_with_model_when_mlflow_available(
        self,
    ) -> None:
        """
        When mlflow is importable, assert exact list + order equality with
        src.ml.model.FEATURE_COLS.  Skipped automatically when mlflow/lightgbm
        are not installed in the test environment.
        """
        mlflow = pytest.importorskip("mlflow", reason="mlflow not installed — skipping exact equality check")
        pytest.importorskip("lightgbm", reason="lightgbm not installed — skipping exact equality check")
        # Both heavy deps present; the module-level set_model() will run on import.
        from src.ml.model import FEATURE_COLS as MODEL_FEATURE_COLS  # noqa: PLC0415
        assert list(_FEATURE_COLS) == list(MODEL_FEATURE_COLS), (
            "baseline._FEATURE_COLS diverged from src/ml/model.py:FEATURE_COLS. "
            "Update the mirror in baseline.py to match exactly."
        )


# ---------------------------------------------------------------------------
# _coerce_feature_frame
# ---------------------------------------------------------------------------


class TestCoerceFeatureFrame:
    def test_bool_column_becomes_float64(self) -> None:
        """A bool column in the input frame is cast to float64 in the result."""
        df = pd.DataFrame({"on_vasopressors": [True, False, True], "score": [1.0, 2.0, 3.0]})
        result = _coerce_feature_frame(df)
        assert str(result["on_vasopressors"].dtype) == "float64"

    def test_true_maps_to_1_and_false_maps_to_0(self) -> None:
        """True → 1.0 and False → 0.0 after coercion."""
        df = pd.DataFrame({"on_ventilator": [True, False]})
        result = _coerce_feature_frame(df)
        assert list(result["on_ventilator"]) == pytest.approx([1.0, 0.0])

    def test_float_column_is_unchanged(self) -> None:
        """A float64 column in the input frame is left unchanged in the result."""
        df = pd.DataFrame({"on_vasopressors": [True, False], "lactate_last": [1.5, 2.5]})
        result = _coerce_feature_frame(df)
        assert str(result["lactate_last"].dtype) == "float64"
        assert list(result["lactate_last"]) == pytest.approx([1.5, 2.5])

    def test_input_frame_is_not_mutated(self) -> None:
        """The original DataFrame must not be modified (immutability)."""
        df = pd.DataFrame({"on_vasopressors": [True, False], "score": [0.1, 0.9]})
        original_dtype = str(df["on_vasopressors"].dtype)
        original_values = list(df["on_vasopressors"])
        _coerce_feature_frame(df)
        assert str(df["on_vasopressors"].dtype) == original_dtype
        assert list(df["on_vasopressors"]) == original_values

    def test_multiple_bool_columns_all_coerced(self) -> None:
        """All bool columns in a mixed DataFrame are coerced to float64."""
        df = pd.DataFrame({
            "on_vasopressors": [True, False],
            "on_ventilator": [False, True],
            "hr_mean": [72.0, 85.0],
        })
        result = _coerce_feature_frame(df)
        assert str(result["on_vasopressors"].dtype) == "float64"
        assert str(result["on_ventilator"].dtype) == "float64"
        assert str(result["hr_mean"].dtype) == "float64"

    def test_no_bool_columns_returns_equivalent_frame(self) -> None:
        """A frame with no bool columns is returned unchanged (values identical)."""
        df = pd.DataFrame({"hr_mean": [70.0, 80.0], "age": [65.0, 72.0]})
        result = _coerce_feature_frame(df)
        assert list(result["hr_mean"]) == pytest.approx([70.0, 80.0])
        assert list(result["age"]) == pytest.approx([65.0, 72.0])

    def test_returns_new_dataframe_object(self) -> None:
        """_coerce_feature_frame always returns a new DataFrame, not the input."""
        df = pd.DataFrame({"on_vasopressors": [True], "score": [0.5]})
        result = _coerce_feature_frame(df)
        assert result is not df


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
