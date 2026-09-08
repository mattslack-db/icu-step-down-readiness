"""
Test the count-mismatch guard in _call_serving.

Databricks Model Serving preserves batch input order; predictions are consumed
positionally.  A count mismatch on a clinical path must hard-fail rather than
silently misalign scores to patients.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from icu_step_down.backend.routers.census import _call_serving


def _make_ws(predictions: list) -> MagicMock:
    """Return a mock WorkspaceClient whose serving endpoint returns *predictions*."""
    ws = MagicMock()
    response = MagicMock()
    response.predictions = predictions
    ws.serving_endpoints.query.return_value = response
    return ws


def test_call_serving_count_mismatch_raises_502() -> None:
    """If the endpoint returns fewer predictions than inputs, raise HTTPException 502."""
    records = [{"hr_mean": 80.0}] * 3   # 3 inputs
    ws = _make_ws([{"prediction": '{"readiness_score": 0.5, "factors": []}'}])  # 1 output

    with pytest.raises(HTTPException) as exc_info:
        _call_serving(ws, records)

    assert exc_info.value.status_code == 502
    assert "1 predictions" in exc_info.value.detail
    assert "3 inputs" in exc_info.value.detail


def test_call_serving_count_match_returns_parsed_predictions() -> None:
    """When counts match, parsed prediction dicts are returned in input order."""
    raw = '{"readiness_score": 0.52, "factors": [{"name": "lactate_last", "direction": "risk", "magnitude": 0.24}]}'
    records = [{"hr_mean": 80.0}, {"hr_mean": 75.0}]
    ws = _make_ws([{"prediction": raw}, {"prediction": raw}])

    result = _call_serving(ws, records)

    assert len(result) == 2
    assert result[0]["readiness_score"] == pytest.approx(0.52)
    assert result[1]["factors"][0]["name"] == "lactate_last"


def test_call_serving_endpoint_exception_raises_502() -> None:
    """If the SDK call itself raises, re-raise as HTTPException 502."""
    ws = MagicMock()
    ws.serving_endpoints.query.side_effect = RuntimeError("connection refused")

    with pytest.raises(HTTPException) as exc_info:
        _call_serving(ws, [{"hr_mean": 80.0}])

    assert exc_info.value.status_code == 502
    assert "connection refused" in exc_info.value.detail
