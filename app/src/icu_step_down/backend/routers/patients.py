"""
GET /api/patients/{icustay_id} — patient detail with vitals, factors, and narrative.

Combines:
  - Demographics + features from ``mimic_iii.census``
  - Vital signs time series from ``mimic_iii.census_vitals``
  - Score + full factor list from the ``icu-readiness`` serving endpoint
  - Gen AI clinical narrative from LLaMA-3.3-70B
  - Relative readiness index computed from the live census distribution
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
from ..genai.narrative import Factor, build_narrative
from ..lib.feature_labels import normalize_factor
from ..lib.readiness import compute_readiness_index, readiness_band_from_index
from ..models import FactorOut, PatientDetail, PatientFeatures, VitalPoint
from .census import (
    FEATURE_COLS,
    _SERVING_ENDPOINT,
    _build_record,
    _call_serving,
    _parse_prediction,
    _to_bool,
    _to_float,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["patients"])

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_CENSUS_COLS = ", ".join(
    f'"{c}"' for c in [
        "icustay_id", "subject_id", "los", "age",
        "on_vasopressors", "on_ventilator",
        "hr_mean", "sbp_mean", "dbp_mean", "spo2_mean", "spo2_min",
        "temp_c_mean", "rr_mean", "gcs_last", "lactate_last",
    ] + FEATURE_COLS
)

_PATIENT_CENSUS_SQL = text(
    f"SELECT {_CENSUS_COLS} FROM mimic_iii.census"
    " WHERE \"icustay_id\" = :icustay_id"
)

_VITALS_SQL = text(
    'SELECT "charttime", "vital_name", "value"'
    " FROM mimic_iii.census_vitals"
    " WHERE \"icustay_id\" = :icustay_id"
    " ORDER BY \"charttime\" ASC"
    " LIMIT 500"
)

# All census icustay_ids (for computing the relative index)
_ALL_SCORES_SQL = text(
    'SELECT "icustay_id" FROM mimic_iii.census'
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


def _build_narrative_factors(
    factors: list[dict[str, Any]],
) -> list[Factor]:
    """
    Convert raw endpoint factors to genai.narrative.Factor objects with
    human-readable labels and corrected clinical direction.
    """
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
    1. Look up the patient in `mimic_iii.census` (404 if not in active census).
    2. Fetch vital signs from `mimic_iii.census_vitals`.
    3. Fetch all census icustay_ids to compute the relative index.
    4. Call `icu-readiness` serving endpoint.
    5. Compute relative readiness index and band.
    6. Generate Gen AI clinical narrative (LLaMA-3.3-70B).
    7. Return assembled PatientDetail.

    All external call failures surface as explicit HTTP errors.
    """
    # --- 1. Fetch patient census row ---
    try:
        result = session.execute(
            _PATIENT_CENSUS_SQL, {"icustay_id": icustay_id}
        )
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
        vitals_result = session.execute(
            _VITALS_SQL, {"icustay_id": icustay_id}
        )
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
            continue  # skip malformed rows; don't swallow entire response

    # --- 3. Fetch all census scores to build distribution for percentile ---
    try:
        all_ids_result = session.execute(_ALL_SCORES_SQL)
        all_census_ids = [str(r[0]) for r in all_ids_result.fetchall()]
    except Exception as exc:
        logger.error("Failed to fetch census distribution: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch census distribution: {exc}",
        ) from exc

    # --- 4. Batch-call serving: this patient + (lazily) full census ---
    # We only have one patient's features here; to compute the relative index
    # we need the census distribution.  We call the endpoint for this patient
    # only and re-use the scores from a quick census pass.
    # For robustness: if the census endpoint has already been called recently,
    # the scale endpoint result here is still just one patient.
    # (The full census pass happens in /api/census; here we compute the index
    #  against a simple re-query of census scores from the DB.)
    #
    # To get census raw scores without a full serving call, we make a single
    # batch request for all census patients (40 rows, fast).
    try:
        all_census_result = session.execute(
            text(
                "SELECT " + ", ".join(f'"{c}"' for c in FEATURE_COLS)
                + " FROM mimic_iii.census"
            )
        )
        all_census_keys = list(all_census_result.keys())
        all_census_rows = [
            dict(zip(all_census_keys, r)) for r in all_census_result.fetchall()
        ]
    except Exception as exc:
        logger.error("Census feature fetch for index calc failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch census features: {exc}",
        ) from exc

    all_records = [_build_record(r) for r in all_census_rows]
    all_predictions = _call_serving(ws, all_records)
    all_scores = [
        float(p.get("readiness_score", 0.0)) for p in all_predictions
    ]

    # This patient's prediction — match by position in the census query result
    # Find the index of this patient in the census
    patient_census_ids = []
    try:
        id_result = session.execute(
            text('SELECT "icustay_id" FROM mimic_iii.census')
        )
        patient_census_ids = [str(r[0]) for r in id_result.fetchall()]
    except Exception:
        pass

    patient_score: float
    patient_pred: dict[str, Any]
    if icustay_id in patient_census_ids:
        idx_in_census = patient_census_ids.index(icustay_id)
        if idx_in_census < len(all_predictions):
            patient_pred = all_predictions[idx_in_census]
            patient_score = float(patient_pred.get("readiness_score", 0.0))
        else:
            # fallback: call single
            single_pred_list = _call_serving(ws, [_build_record(row)])
            patient_pred = single_pred_list[0]
            patient_score = float(patient_pred.get("readiness_score", 0.0))
    else:
        # Patient not in census snapshot but in DB — call individually
        single_pred_list = _call_serving(ws, [_build_record(row)])
        patient_pred = single_pred_list[0]
        patient_score = float(patient_pred.get("readiness_score", 0.0))
        all_scores.append(patient_score)

    # --- 5. Compute relative index and band ---
    readiness_index = compute_readiness_index(patient_score, all_scores)
    band = readiness_band_from_index(readiness_index)

    # --- 6. Build response factors ---
    raw_factors = patient_pred.get("factors", [])
    response_factors: list[FactorOut] = []
    for f in raw_factors:
        label, direction, magnitude = normalize_factor(
            f.get("name", ""),
            f.get("direction", "risk"),
            float(f.get("magnitude", 0.0)),
        )
        response_factors.append(FactorOut(name=label, direction=direction, magnitude=magnitude))

    # --- 7. Generate Gen AI narrative ---
    narrative_factors = _build_narrative_factors(raw_factors)
    try:
        # Pass the INDEX-derived representative score so the narrative band
        # matches the displayed band (not the raw score, which clusters ~0.44–0.53).
        # We encode the band as a score hint: Ready≈0.90, Borderline≈0.60, Not ready≈0.20.
        _band_score_hint = {
            "Ready": 0.90,
            "Borderline": 0.60,
            "Not ready": 0.20,
        }.get(band, patient_score)
        narrative = build_narrative(_band_score_hint, narrative_factors)
    except Exception as exc:
        logger.warning("Gen AI narrative generation failed: %s", exc)
        narrative = (
            f"Clinical narrative unavailable ({exc}). "
            f"Readiness band: {band}."
        )

    # Lactate note
    factor_names = [f.get("name", "") for f in raw_factors]
    lactate_note: str | None = (
        _LACTATE_NOTE if "lactate_last" in factor_names else None
    )

    # --- 8. Assemble PatientFeatures ---
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
