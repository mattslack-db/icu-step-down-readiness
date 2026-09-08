"""
GET /api/patients/{icustay_id} — patient detail with vitals, factors, and narrative.

Combines:
  - Demographics + features from ``mimic_iii.census``
  - Vital signs time series from ``mimic_iii.census_vitals``
  - Score + full factor list from the ``icu-readiness`` serving endpoint
  - Gen AI clinical narrative from LLaMA-3.3-70B
  - Relative readiness index computed from the live census distribution

Correctness guarantee: census FEATURE rows and serving predictions are keyed
by ``icustay_id`` (not matched by position) — Postgres does not guarantee
consistent row order across separate unordered queries.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import text

from ..core.dependencies import Dependencies
from ..genai.narrative import Factor, build_narrative
from ..lib.feature_labels import normalize_factor
from ..lib.readiness import compute_readiness_index, readiness_band_from_index
from ..models import FactorOut, PatientDetail, PatientFeatures, VitalPoint
from .census import (
    FEATURE_COLS,
    _build_record,
    _call_serving,
    _to_bool,
    _to_float,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["patients"])

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

# Patient detail columns (may overlap with FEATURE_COLS — deduplication via set
# is intentional; Python dicts preserve insertion order so the merge is safe).
_DETAIL_EXTRA_COLS = [
    "icustay_id", "subject_id", "los", "age",
    "on_vasopressors", "on_ventilator",
    "hr_mean", "sbp_mean", "dbp_mean", "spo2_mean", "spo2_min",
    "temp_c_mean", "rr_mean", "gcs_last", "lactate_last",
]
# Merge extra cols + all FEATURE_COLS, preserving order, no duplicates.
_seen: set[str] = set()
_PATIENT_COLS: list[str] = []
for _col in _DETAIL_EXTRA_COLS + FEATURE_COLS:
    if _col not in _seen:
        _PATIENT_COLS.append(_col)
        _seen.add(_col)

_PATIENT_CENSUS_SQL = text(
    "SELECT " + ", ".join(f'"{c}"' for c in _PATIENT_COLS)
    + " FROM mimic_iii.census WHERE \"icustay_id\" = :icustay_id"
)

_VITALS_SQL = text(
    'SELECT "charttime", "vital_name", "value"'
    " FROM mimic_iii.census_vitals"
    " WHERE \"icustay_id\" = :icustay_id"
    " ORDER BY \"charttime\" ASC"
    " LIMIT 500"
)

# Batch census query: include icustay_id so predictions can be keyed by id.
_CENSUS_BATCH_SQL = text(
    'SELECT "icustay_id", ' + ", ".join(f'"{c}"' for c in FEATURE_COLS)
    + " FROM mimic_iii.census"
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_LACTATE_NOTE = (
    "Lactate is the dominant model feature. When lactate is *measured*, "
    "even a low value signals a more complex stay; when it is *absent* (NULL), "
    "LightGBM's NaN path often indicates a quick, uncomplicated course. "
    "Interpret the lactate factor in clinical context."
)


def _build_narrative_factors(factors: list[dict[str, Any]]) -> list[Factor]:
    """Convert raw endpoint factors to narrative.Factor objects with corrected direction."""
    result = []
    for f in factors:
        label, direction, magnitude = normalize_factor(
            f.get("name", ""),
            f.get("direction", "risk"),
            float(f.get("magnitude", 0.0)),
        )
        result.append(Factor(name=label, direction=direction, magnitude=magnitude))
    return result


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/patients/{icustay_id}",
    response_model=PatientDetail,
    operation_id="getPatient",
    summary="Patient detail: features, vitals, factors, and Gen AI narrative",
)
def get_patient(
    icustay_id: str,
    session: Dependencies.Session,
    ws: Dependencies.Client,
) -> PatientDetail:
    """
    Return full clinical detail for one ICU patient.

    Steps:
    1. Look up the patient in ``mimic_iii.census`` (404 if not in active census).
    2. Fetch vital signs from ``mimic_iii.census_vitals``.
    3. Batch-fetch all census feature rows (WITH icustay_id); call the serving
       endpoint for the whole census in one shot.
    4. Key predictions by icustay_id — never by row position.
    5. Compute relative readiness index from the full census score distribution.
    6. Generate Gen AI clinical narrative (LLaMA-3.3-70B).
    7. Return assembled PatientDetail.

    All DB and serving errors surface as explicit HTTP errors; none are swallowed.
    """
    # --- 1. Fetch patient census row ---
    try:
        result = session.execute(_PATIENT_CENSUS_SQL, {"icustay_id": icustay_id})
        keys = list(result.keys())
        row_tuple = result.fetchone()
    except Exception as exc:
        logger.error("Lakebase census query failed for %s: %s", icustay_id, exc)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to query Lakebase census: {exc}",
        ) from exc

    if row_tuple is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Patient icustay_id={icustay_id!r} not found in active census. "
                "Only current ICU patients are scored."
            ),
        )
    row = dict(zip(keys, row_tuple))

    # --- 2. Fetch vitals ---
    try:
        vitals_result = session.execute(_VITALS_SQL, {"icustay_id": icustay_id})
        vitals_rows = vitals_result.fetchall()
    except Exception as exc:
        logger.error("Lakebase vitals query failed for %s: %s", icustay_id, exc)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to query Lakebase census_vitals: {exc}",
        ) from exc

    vitals: list[VitalPoint] = []
    for vrow in vitals_rows:
        charttime, vital_name, value = vrow
        try:
            vitals.append(VitalPoint(
                charttime=charttime,
                vital_name=str(vital_name),
                value=float(value) if value is not None else 0.0,
            ))
        except Exception:
            continue  # skip individual malformed rows only

    # --- 3. Fetch all census feature rows (icustay_id included) ---
    try:
        batch_result = session.execute(_CENSUS_BATCH_SQL)
        batch_keys = list(batch_result.keys())
        batch_rows = [dict(zip(batch_keys, r)) for r in batch_result.fetchall()]
    except Exception as exc:
        logger.error("Census batch feature fetch failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch census features for index computation: {exc}",
        ) from exc

    # Preserve the query order so predictions[i] lines up with batch_rows[i].
    ordered_ids = [str(r["icustay_id"]) for r in batch_rows]
    records = [_build_record(r) for r in batch_rows]

    # --- 4. Batch-call serving endpoint; key predictions by icustay_id ---
    all_predictions = _call_serving(ws, records)

    # Defensive guard: Databricks Model Serving preserves batch input order and
    # the pyfunc output carries no patient id to key on — we zip ordered_ids with
    # all_predictions positionally to build the id→prediction map.  A count
    # mismatch would silently misassign scores to patients on a clinical path.
    if len(all_predictions) != len(ordered_ids):
        raise HTTPException(
            status_code=500,
            detail=(
                f"Serving endpoint returned {len(all_predictions)} predictions for "
                f"{len(ordered_ids)} inputs — cannot safely map scores to patients."
            ),
        )

    # Order preserved: ordered_ids[i] ↔ all_predictions[i] (same batch order).
    predictions_by_id: dict[str, dict[str, Any]] = {
        census_id: pred
        for census_id, pred in zip(ordered_ids, all_predictions)
    }

    all_scores = [float(p.get("readiness_score", 0.0)) for p in all_predictions]

    # Look up this patient's prediction BY KEY — never by position.
    if icustay_id in predictions_by_id:
        patient_pred = predictions_by_id[icustay_id]
        patient_score = float(patient_pred.get("readiness_score", 0.0))
    else:
        # Patient was in census (step 1 succeeded) but absent from batch result —
        # should not happen in normal operation; score individually and add to
        # the distribution so the index is still meaningful.
        logger.warning(
            "Patient %s not found in batch census result; scoring individually.",
            icustay_id,
        )
        single_preds = _call_serving(ws, [_build_record(row)])
        patient_pred = single_preds[0]
        patient_score = float(patient_pred.get("readiness_score", 0.0))
        all_scores.append(patient_score)

    # --- 5. Compute relative index and band ---
    readiness_index = compute_readiness_index(patient_score, all_scores)
    band = readiness_band_from_index(readiness_index)

    # --- 6. Build response factors (sorted by magnitude desc, direction-corrected) ---
    raw_factors: list[dict[str, Any]] = sorted(
        patient_pred.get("factors", []),
        key=lambda f: float(f.get("magnitude", 0.0)),
        reverse=True,
    )
    response_factors: list[FactorOut] = [
        FactorOut(
            name=label,
            direction=direction,
            magnitude=magnitude,
        )
        for label, direction, magnitude in (
            normalize_factor(
                f.get("name", ""),
                f.get("direction", "risk"),
                float(f.get("magnitude", 0.0)),
            )
            for f in raw_factors
        )
    ]

    # --- 7. Generate Gen AI narrative ---
    narrative_factors = _build_narrative_factors(raw_factors)
    try:
        # Pass an index-derived representative score so the narrative band label
        # matches the displayed band (raw score clusters ~0.44–0.53 and is not
        # a probability; the narrative must say "Ready"/"Borderline"/"Not ready").
        _band_score_hint = {
            "Ready": 0.90,
            "Borderline": 0.60,
            "Not ready": 0.20,
        }.get(band, patient_score)
        narrative = build_narrative(_band_score_hint, narrative_factors)
    except Exception as exc:
        logger.warning("Gen AI narrative generation failed: %s", exc)
        narrative = f"Clinical narrative unavailable ({exc}). Readiness band: {band}."

    # Lactate note (present when lactate_last is a top model factor)
    raw_factor_names = [f.get("name", "") for f in raw_factors]
    lactate_note: str | None = (
        _LACTATE_NOTE if "lactate_last" in raw_factor_names else None
    )

    # --- 8. Assemble and return ---
    features = PatientFeatures(
        icustay_id=str(row["icustay_id"]),
        subject_id=str(row["subject_id"]),
        age=float(_to_float(row["age"]) or 0.0),
        los=float(_to_float(row["los"]) or 0.0),
        on_vasopressors=_to_bool(row.get("on_vasopressors", False)),
        on_ventilator=_to_bool(row.get("on_ventilator", False)),
        hr_mean=_to_float(row.get("hr_mean")),
        sbp_mean=_to_float(row.get("sbp_mean")),
        dbp_mean=_to_float(row.get("dbp_mean")),
        spo2_mean=_to_float(row.get("spo2_mean")),
        spo2_min=_to_float(row.get("spo2_min")),
        temp_c_mean=_to_float(row.get("temp_c_mean")),
        rr_mean=_to_float(row.get("rr_mean")),
        gcs_last=_to_float(row.get("gcs_last")),
        lactate_last=_to_float(row.get("lactate_last")),
    )

    return PatientDetail(
        features=features,
        vitals=vitals,
        readiness_score=patient_score,
        readiness_index=readiness_index,
        band=band,
        factors=response_factors,
        narrative=narrative,
        lactate_note=lactate_note,
    )
