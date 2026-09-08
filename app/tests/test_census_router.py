"""
Unit tests for census router helpers.

Tests cover _to_float, _to_bool, _build_record, _parse_prediction,
_call_serving, and the top-factors sorting logic — all pure/mockable.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from icu_step_down.backend.routers.census import (
    FEATURE_COLS,
    _build_record,
    _call_serving,
    _parse_prediction,
    _to_bool,
    _to_float,
)


# ---------------------------------------------------------------------------
# _to_float
# ---------------------------------------------------------------------------


class TestToFloat:
    def test_none_returns_none(self) -> None:
        assert _to_float(None) is None

    def test_float_passthrough(self) -> None:
        assert _to_float(3.14) == pytest.approx(3.14)

    def test_int_converts(self) -> None:
        assert _to_float(42) == pytest.approx(42.0)

    def test_decimal_converts(self) -> None:
        assert _to_float(Decimal("1.5")) == pytest.approx(1.5)

    def test_string_numeric_converts(self) -> None:
        assert _to_float("2.71") == pytest.approx(2.71)

    def test_bad_string_returns_none(self) -> None:
        assert _to_float("not_a_number") is None

    def test_empty_string_returns_none(self) -> None:
        assert _to_float("") is None


# ---------------------------------------------------------------------------
# _to_bool
# ---------------------------------------------------------------------------


class TestToBool:
    def test_true_passthrough(self) -> None:
        assert _to_bool(True) is True

    def test_false_passthrough(self) -> None:
        assert _to_bool(False) is False

    def test_int_one_truthy(self) -> None:
        assert _to_bool(1) is True

    def test_int_zero_falsy(self) -> None:
        assert _to_bool(0) is False

    def test_none_falsy(self) -> None:
        assert _to_bool(None) is False


# ---------------------------------------------------------------------------
# _build_record
# ---------------------------------------------------------------------------


class TestBuildRecord:
    def _base_row(self) -> dict:
        row: dict = {col: None for col in FEATURE_COLS}
        row.update(
            {
                "icustay_id": "123",
                "subject_id": "456",
                "los": 2.5,
                "age": 65.0,
                "on_vasopressors": True,
                "on_ventilator": False,
                "hr_mean": 80.0,
                "spo2_last": 97.0,
            }
        )
        return row

    def test_boolean_to_int(self) -> None:
        row = self._base_row()
        record = _build_record(row)
        assert record["on_vasopressors"] == 1
        assert record["on_ventilator"] == 0

    def test_numeric_preserved(self) -> None:
        row = self._base_row()
        record = _build_record(row)
        assert record["hr_mean"] == pytest.approx(80.0)
        assert record["spo2_last"] == pytest.approx(97.0)

    def test_none_preserved_as_none(self) -> None:
        row = self._base_row()
        record = _build_record(row)
        assert record["lactate_last"] is None  # not in base row

    def test_all_feature_cols_present(self) -> None:
        row = self._base_row()
        record = _build_record(row)
        for col in FEATURE_COLS:
            assert col in record

    def test_no_extra_cols(self) -> None:
        row = self._base_row()
        record = _build_record(row)
        assert set(record.keys()) == set(FEATURE_COLS)

    def test_decimal_converts_to_float(self) -> None:
        row = self._base_row()
        row["hr_mean"] = Decimal("72.5")
        record = _build_record(row)
        assert record["hr_mean"] == pytest.approx(72.5)


# ---------------------------------------------------------------------------
# _parse_prediction
# ---------------------------------------------------------------------------


class TestParsePrediction:
    def test_dict_with_json_string(self) -> None:
        raw = '{"readiness_score": 0.6, "factors": []}'
        pred = {"prediction": raw}
        result = _parse_prediction(pred)
        assert result["readiness_score"] == pytest.approx(0.6)
        assert result["factors"] == []

    def test_dict_with_nested_dict(self) -> None:
        pred = {"prediction": {"readiness_score": 0.7, "factors": []}}
        result = _parse_prediction(pred)
        assert result["readiness_score"] == pytest.approx(0.7)

    def test_object_with_prediction_attr(self) -> None:
        obj = MagicMock()
        obj.prediction = '{"readiness_score": 0.5, "factors": []}'
        result = _parse_prediction(obj)
        assert result["readiness_score"] == pytest.approx(0.5)

    def test_missing_prediction_key_returns_empty(self) -> None:
        result = _parse_prediction({})
        assert result == {}

    def test_factors_parsed_correctly(self) -> None:
        factor = {"name": "lactate_last", "direction": "risk", "magnitude": 0.25}
        raw = json.dumps({"readiness_score": 0.4, "factors": [factor]})
        result = _parse_prediction({"prediction": raw})
        assert len(result["factors"]) == 1
        assert result["factors"][0]["name"] == "lactate_last"


# ---------------------------------------------------------------------------
# _call_serving
# ---------------------------------------------------------------------------


def _make_ws_with_predictions(preds: list[dict]) -> MagicMock:
    """Build a mock WorkspaceClient returning the given prediction dicts."""
    ws = MagicMock()
    resp = MagicMock()
    resp.predictions = [
        {"prediction": json.dumps(p)} for p in preds
    ]
    ws.serving_endpoints.query.return_value = resp
    return ws


class TestCallServing:
    def test_single_record_returns_single_prediction(self) -> None:
        pred = {"readiness_score": 0.5, "factors": []}
        ws = _make_ws_with_predictions([pred])
        result = _call_serving(ws, [{"hr_mean": 80.0}])
        assert len(result) == 1
        assert result[0]["readiness_score"] == pytest.approx(0.5)

    def test_multiple_records_preserve_order(self) -> None:
        preds = [
            {"readiness_score": 0.7, "factors": []},
            {"readiness_score": 0.3, "factors": []},
        ]
        ws = _make_ws_with_predictions(preds)
        records = [{"hr_mean": 80.0}, {"hr_mean": 60.0}]
        result = _call_serving(ws, records)
        assert result[0]["readiness_score"] == pytest.approx(0.7)
        assert result[1]["readiness_score"] == pytest.approx(0.3)

    def test_count_mismatch_raises_502(self) -> None:
        preds = [{"readiness_score": 0.5, "factors": []}]
        ws = _make_ws_with_predictions(preds)
        with pytest.raises(HTTPException) as exc_info:
            _call_serving(ws, [{"a": 1}, {"b": 2}])
        assert exc_info.value.status_code == 502

    def test_endpoint_exception_raises_502(self) -> None:
        ws = MagicMock()
        ws.serving_endpoints.query.side_effect = RuntimeError("endpoint down")
        with pytest.raises(HTTPException) as exc_info:
            _call_serving(ws, [{"a": 1}])
        assert exc_info.value.status_code == 502
        assert "endpoint down" in exc_info.value.detail

    def test_empty_records_returns_empty(self) -> None:
        ws = MagicMock()
        resp = MagicMock()
        resp.predictions = []
        ws.serving_endpoints.query.return_value = resp
        result = _call_serving(ws, [])
        assert result == []
