"""Route-level tests: active life support (last 24h) never shows as 'Ready'.

A patient ventilated or on vasopressors in the last 24h can rank high on other
signals; the census list and analytics must cap their band at Borderline and
surface the life-support risk, regardless of score.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from icu_step_down.backend.routers.analytics import get_analytics
from icu_step_down.backend.routers.census import FEATURE_COLS, get_census


def _row(icustay_id: str, **flags) -> dict:
    row = {"icustay_id": icustay_id, "subject_id": f"P-{icustay_id}", "los": 2.0, "age": 60,
           "on_vasopressors": False, "on_ventilator": False}
    for col in FEATURE_COLS:
        row.setdefault(col, None)
    row.update({"vasopressors_24h": False, "ventilated_24h": False})
    row.update(flags)
    return row


def _session(rows: list[dict]) -> MagicMock:
    session = MagicMock()

    def _execute(query, params=None):
        result = MagicMock()
        result.keys.return_value = list(rows[0].keys())
        result.fetchall.return_value = [tuple(r[k] for k in rows[0]) for r in rows]
        result.fetchone.return_value = None
        return result

    session.execute.side_effect = _execute
    return session


def _ws(scores: list[float]) -> MagicMock:
    ws = MagicMock()
    ws.config.client_id = None
    ws.serving_endpoints.query.return_value.predictions = [
        {"prediction": json.dumps({"readiness_score": s,
                                   "factors": [{"name": "gcs_last", "direction": "supports", "magnitude": 0.3}]})}
        for s in scores
    ]
    return ws


def _cohort() -> list[dict]:
    # Highest score belongs to a patient ventilated in the last 24h.
    return [_row("1", ventilated_24h=True), _row("2"), _row("3"), _row("4"), _row("5"), _row("6")]


# n=6 → indices 83, 67, 50, 33, 17, 0: the top two would both be Ready uncapped.
SCORES = [0.99, 0.95, 0.60, 0.50, 0.30, 0.10]


def test_census_caps_ventilated_top_scorer_at_borderline_and_shows_the_risk():
    resp = get_census(_session(_cohort()), _ws(SCORES), None)
    top = next(p for p in resp.patients if p.icustay_id == "1")
    assert top.readiness_index >= 66          # still ranked highest — index is unchanged
    assert top.band == "Borderline"           # but never banded Ready
    assert top.top_factors[0].name == "ventilated in last 24h"
    assert top.top_factors[0].direction == "risk"
    assert len(top.top_factors) <= 3


def test_census_uncapped_patient_keeps_ready():
    resp = get_census(_session(_cohort()), _ws(SCORES), None)
    second = next(p for p in resp.patients if p.icustay_id == "2")
    assert second.readiness_index >= 66 and second.band == "Ready"


def test_analytics_band_distribution_applies_the_cap():
    resp = get_analytics(_session(_cohort()), _ws(SCORES), None)
    counts = {b.band: b.count for b in resp.band_distribution}
    assert counts["Ready"] == 1       # "1" (83) capped → Borderline; only "2" (67) is Ready
    assert counts["Borderline"] == 3   # "1" capped + indices 50 and 33
