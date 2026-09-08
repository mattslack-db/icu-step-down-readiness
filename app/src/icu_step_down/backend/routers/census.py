"""
GET /api/census — current ICU census ranked by relative readiness index.

Queries Lakebase `mimic_iii.census` for the 40 current patients, batch-calls
the ``icu-readiness`` serving endpoint, computes per-patient percentile ranks
within the cohort, and returns the list sorted by readiness_index descending.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter, HTTPException
from sqlmodel import text

from ..core.dependencies import Dependencies
from ..lib.feature_labels import normalize_factor
from ..lib.readiness import compute_readiness_index, readiness_band_from_index
from ..models import CensusPatient, CensusResponse, FactorOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["census"])

# ---------------------------------------------------------------------------
# Feature columns sent to the serving endpoint (exact order required by model).
# ---------------------------------------------------------------------------

FEATURE_COLS: list[str] = [
    "hr_mean", "hr_min", "hr_max", "hr_last",
    "sbp_mean", "sbp_min", "sbp_max", "sbp_last",
    "dbp_mean", "dbp_min", "dbp_max", "dbp_last",
    "spo2_mean", "spo2_min", "spo2_max", "spo2_last",
    "temp_c_mean", "temp_c_min", "temp_c_max", "temp_c_last",
    "rr_mean", "rr_min", "rr_max", "rr_last",
    "on_vasopressors", "on_ventilator",
    "gcs_last", "lactate_last", "los", "age",
]

_SELECT_COLS = ", ".join(
    f'"{c}"' for c in ["icustay_id", "subject_id", "los", "age",
                       "on_vasopressors", "on_ventilator"]
    + FEATURE_COLS
)

_CENSUS_SQL = text(f"SELECT {_SELECT_COLS} FROM mimic_iii.census")

_SERVING_ENDPOINT = "icu-readiness"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(val: Any) -> float | None:
    """Convert a Postgres value (str, Decimal, int, float, None) to Python float."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_bool(val: Any) -> bool:
    """Postgres returns booleans as Python bool; coerce any truthy int too."""
    if isinstance(val, bool):
        return val
    return bool(val)


def _build_record(row: dict[str, Any]) -> dict[str, Any]:
    """
    Build a serving-endpoint record from a census row.

    Boolean columns are sent as 0/1 integers (model was trained with ints).
    NULL feature values are sent as None (LightGBM handles NaN natively).
    """
    record: dict[str, Any] = {}
    for col in FEATURE_COLS:
        val = row.get(col)
        if col in ("on_vasopressors", "on_ventilator"):
            record[col] = 1 if _to_bool(val) else 0
        else:
            record[col] = _to_float(val)
    return record


def _parse_prediction(pred: Any) -> dict[str, Any]:
    """
    Parse one prediction item from QueryEndpointResponse.predictions.

    The MLflow pyfunc model returns each prediction as a dict with key
    ``"prediction"`` containing a JSON string.  Handle both dict and
    object forms defensively.
    """
    if isinstance(pred, dict):
        raw = pred.get("prediction", "{}")
    else:
        raw = getattr(pred, "prediction", "{}")
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, dict):
        return raw
    return {}


def _call_serving(
    ws: WorkspaceClient,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Batch-call the ``icu-readiness`` serving endpoint.

    Returns a list of parsed prediction dicts, one per input record, in
    the same order.  Each dict has ``readiness_score`` (float) and
    ``factors`` (list of {name, direction, magnitude}).

    Raises:
        HTTPException 502 if the serving endpoint call fails.
    """
    try:
        response = ws.serving_endpoints.query(
            _SERVING_ENDPOINT,
            dataframe_records=records,
        )
    except Exception as exc:
        logger.error("Serving endpoint call failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Model serving endpoint '{_SERVING_ENDPOINT}' unavailable: {exc}",
        ) from exc

    predictions = response.predictions or []
    if len(predictions) != len(records):
        raise HTTPException(
            status_code=502,
            detail=(
                f"Serving endpoint returned {len(predictions)} predictions "
                f"for {len(records)} inputs — mismatch."
            ),
        )
    return [_parse_prediction(p) for p in predictions]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/census",
    response_model=CensusResponse,
    operation_id="getCensus",
    summary="Current ICU census ranked by readiness index",
)
def get_census(
    session: Dependencies.Session,
    ws: Dependencies.Client,
) -> CensusResponse:
    """
    Return all current ICU patients ranked by relative readiness index (desc).

    Steps:
    1. Query Lakebase `mimic_iii.census` for all 40 patients.
    2. Batch-call the `icu-readiness` serving endpoint.
    3. Compute each patient's percentile rank within the cohort.
    4. Sort by index desc and return.

    Errors from Lakebase or the serving endpoint are surfaced explicitly
    (HTTP 502 with a descriptive message) — never swallowed.
    """
    # --- 1. Fetch census rows ---
    try:
        result = session.execute(_CENSUS_SQL)
        keys = list(result.keys())
        rows = [dict(zip(keys, row)) for row in result.fetchall()]
    except Exception as exc:
        logger.error("Lakebase census query failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to query Lakebase census table: {exc}",
        ) from exc

    if not rows:
        return CensusResponse(
            patients=[],
            total=0,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # --- 2. Build serving records and call endpoint ---
    records = [_build_record(row) for row in rows]
    predictions = _call_serving(ws, records)

    # --- 3. Compute relative readiness indices ---
    raw_scores = [
        float(pred.get("readiness_score", 0.0)) for pred in predictions
    ]
    indices = [
        compute_readiness_index(s, raw_scores) for s in raw_scores
    ]

    # --- 4. Build patient summaries ---
    patients: list[CensusPatient] = []
    for row, pred, idx in zip(rows, predictions, indices):
        raw_score = float(pred.get("readiness_score", 0.0))
        band = readiness_band_from_index(idx)

        # Top-3 factors by magnitude (explicit sort — model returns top-5 by
        # magnitude already, but sort here makes the guarantee explicit).
        raw_factors = sorted(
            pred.get("factors", []),
            key=lambda f: float(f.get("magnitude", 0.0)),
            reverse=True,
        )
        top_factors: list[FactorOut] = []
        for f in raw_factors[:3]:
            label, direction, magnitude = normalize_factor(
                f.get("name", ""),
                f.get("direction", "risk"),
                float(f.get("magnitude", 0.0)),
            )
            top_factors.append(FactorOut(
                name=label,
                direction=direction,
                magnitude=magnitude,
            ))

        patients.append(
            CensusPatient(
                icustay_id=str(row["icustay_id"]),
                subject_id=str(row["subject_id"]),
                age=float(_to_float(row["age"]) or 0.0),
                los=float(_to_float(row["los"]) or 0.0),
                readiness_score=raw_score,
                readiness_index=idx,
                band=band,
                on_vasopressors=_to_bool(row.get("on_vasopressors", False)),
                on_ventilator=_to_bool(row.get("on_ventilator", False)),
                top_factors=top_factors,
            )
        )

    # Sort by readiness_index descending (highest first)
    patients.sort(key=lambda p: p.readiness_index, reverse=True)

    return CensusResponse(
        patients=patients,
        total=len(patients),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
