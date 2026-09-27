"""
Route-level tests for care-unit access enforcement on the Lakebase read paths.

These verify the wiring in census/analytics/patients:
  - a fail-closed deny scope ([]) short-circuits to an empty result / 404
    WITHOUT querying Lakebase or the serving endpoint;
  - a restricted scope (["MICU"]) appends a bound-parameter care_unit predicate
    to the executed SQL.

The pure clause-building logic is covered in tests/lib/test_access.py; here we
assert the routes actually apply it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from icu_step_down.backend.routers.analytics import get_analytics
from icu_step_down.backend.routers.census import get_census
from icu_step_down.backend.routers.patients import get_patient


class _RecordingSession:
    """Mock session that records executed (sql, params) and returns given rows."""

    def __init__(
        self,
        rows: list[tuple] | None = None,
        keys: list[str] | None = None,
        fetchone_value: tuple | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self._rows = rows or []
        self._keys = keys or []
        self._fetchone = fetchone_value

    def execute(self, query: Any, params: dict[str, Any] | None = None) -> MagicMock:
        self.calls.append((str(query), params))
        result = MagicMock()
        result.keys.return_value = self._keys
        result.fetchall.return_value = self._rows
        result.fetchone.return_value = self._fetchone
        return result


def _exploding_ws() -> MagicMock:
    """A workspace client that fails if the serving endpoint is ever called."""
    ws = MagicMock()
    ws.serving_endpoints.query.side_effect = AssertionError(
        "serving endpoint must not be called on a denied request"
    )
    return ws


# ---------------------------------------------------------------------------
# Fail-closed deny ([]): short-circuit, no query, no serving call
# ---------------------------------------------------------------------------


class TestDenyShortCircuits:
    def test_census_deny_returns_empty_without_querying(self) -> None:
        session = _RecordingSession()
        resp = get_census(session, _exploding_ws(), [])
        assert resp.total == 0
        assert resp.patients == []
        assert session.calls == []  # never touched Lakebase

    def test_analytics_deny_returns_empty_without_querying(self) -> None:
        session = _RecordingSession()
        resp = get_analytics(session, _exploding_ws(), [])
        assert resp.total_census == 0
        assert resp.band_distribution == []
        assert resp.drift_status is None
        assert session.calls == []

    def test_patient_deny_returns_404_without_querying(self) -> None:
        session = _RecordingSession()
        with pytest.raises(HTTPException) as exc:
            get_patient("224403", session, _exploding_ws(), [])
        assert exc.value.status_code == 404
        assert session.calls == []


# ---------------------------------------------------------------------------
# Restricted scope: care_unit predicate is applied to the executed SQL
# ---------------------------------------------------------------------------


class TestScopeAppliesFilter:
    def test_census_scope_appends_care_unit_predicate(self) -> None:
        # Return no rows so the route returns early (no serving call needed).
        session = _RecordingSession(rows=[], keys=[])
        resp = get_census(session, MagicMock(), ["MICU"])
        assert resp.total == 0
        sql, params = session.calls[0]
        assert '"care_unit" IN (:cu_0)' in sql
        assert params == {"cu_0": "MICU"}

    def test_analytics_scope_appends_care_unit_predicate(self) -> None:
        session = _RecordingSession(rows=[], keys=[])
        get_analytics(session, MagicMock(), ["SICU"])
        sql, params = session.calls[0]
        assert '"care_unit" IN (:cu_0)' in sql
        assert params == {"cu_0": "SICU"}

    def test_patient_scope_appends_and_predicate_and_binds_id(self) -> None:
        # Detail lookup returns no row → patient not in the user's unit → 404.
        session = _RecordingSession(fetchone_value=None)
        with pytest.raises(HTTPException) as exc:
            get_patient("224403", session, MagicMock(), ["MICU"])
        assert exc.value.status_code == 404
        sql, params = session.calls[0]
        assert 'WHERE "icustay_id" = :icustay_id AND "care_unit" IN (:cu_0)' in sql
        assert params == {"icustay_id": "224403", "cu_0": "MICU"}


class TestUnrestrictedScopeAddsNoFilter:
    """scope=None (enforcement OFF or admin) → SQL identical to unfiltered query."""

    def test_census_none_scope_has_no_care_unit_predicate(self) -> None:
        session = _RecordingSession(rows=[], keys=[])
        get_census(session, MagicMock(), None)
        sql, params = session.calls[0]
        assert "care_unit" not in sql
        assert params == {}

    def test_analytics_none_scope_has_no_care_unit_predicate(self) -> None:
        session = _RecordingSession(rows=[], keys=[])
        get_analytics(session, MagicMock(), None)
        sql, params = session.calls[0]
        assert "care_unit" not in sql
        assert params == {}

    def test_patient_none_scope_binds_only_id(self) -> None:
        # No row → 404, but the executed detail SQL must carry no care_unit filter.
        session = _RecordingSession(fetchone_value=None)
        with pytest.raises(HTTPException):
            get_patient("224403", session, MagicMock(), None)
        sql, params = session.calls[0]
        assert "care_unit" not in sql
        assert " AND " not in sql
        assert params == {"icustay_id": "224403"}
