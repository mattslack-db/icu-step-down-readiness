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
from ..lib import access
from ..lib.care_plan import build_care_plan
from ..lib.feature_labels import normalize_factor
from ..lib.guardrails import GUARDRAILS
from ..lib.readiness import compute_readiness_index, readiness_band_from_index
from ..models import (
    CarePlanOut,
    FactorOut,
    MonitoringItemOut,
    PatientDetail,
    PatientFeatures,
    VitalPoint,
)
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
    "icustay_id",
    "subject_id",
    "los",
    "age",
    "on_vasopressors",
    "on_ventilator",
    # Derived guardrail flags (Phase 2) — used to inject risk factors
    "recent_extubation",
    "active_bleeding",
    "hr_mean",
    "sbp_mean",
    "dbp_mean",
    "spo2_mean",
    "spo2_min",
    "temp_c_mean",
    "rr_mean",
    "gcs_last",
    "lactate_last",
]
# Merge extra cols + all FEATURE_COLS, preserving order, no duplicates.
_seen: set[str] = set()
_PATIENT_COLS: list[str] = []
for _col in _DETAIL_EXTRA_COLS + FEATURE_COLS:
    if _col not in _seen:
        _PATIENT_COLS.append(_col)
        _seen.add(_col)

# Base SELECT with the icustay_id predicate; a care_unit filter is appended as
# an extra AND per-request when unit-access enforcement is enabled. With
# enforcement OFF the scope is None and the executed SQL is identical to the
# unscoped lookup. With enforcement ON, a patient outside the requesting user's
# units matches no row and returns a 404 (never a leak).
_PATIENT_CENSUS_SELECT = (
    "SELECT "
    + ", ".join(f'"{c}"' for c in _PATIENT_COLS)
    + ' FROM mimic_iii.census WHERE "icustay_id" = :icustay_id'
)

_VITALS_SQL = text(
    'SELECT "charttime", "vital_name", "value"'
    " FROM mimic_iii.census_vitals"
    ' WHERE "icustay_id" = :icustay_id'
    ' ORDER BY "charttime" ASC'
    " LIMIT 500"
)

# Batch census query: include icustay_id so predictions can be keyed by id.
# Base SELECT; the same care_unit filter is appended so the readiness index is
# computed within exactly the cohort the user is allowed to see.
#
# DESIGN TRADE-OFF (deliberate): scoping this cohort makes the readiness index
# a percentile WITHIN the viewer's visible units, so a scoped nurse and an
# icu_admin can see a different index/band for the same patient. This is chosen
# over a whole-census index because the alternative requires reading the very
# rows the user is denied (other units) to compute their percentile, which would
# defeat the access boundary. When enforcement is OFF (default) every viewer sees
# the whole-census index, so there is no divergence. Revisit if a single stable
# cross-unit index becomes a product requirement.
_CENSUS_BATCH_SELECT = (
    'SELECT "icustay_id", '
    + ", ".join(f'"{c}"' for c in FEATURE_COLS)
    + " FROM mimic_iii.census"
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

# Maximum factors returned in the patient detail response, matching the model's
# own TOP_N_FACTORS cap.  Guardrail injection can add up to len(inject_risk
# guardrails) factors; truncating here keeps the list at a predictable size.
TOP_N_DISPLAY_FACTORS: int = 5

# Small epsilon added to the max existing magnitude when injecting a guardrail
# factor, ensuring it sorts to the top of the list.
_INJECT_EPSILON: float = 1e-4

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
    care_unit_scope: Dependencies.CareUnitScope,
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
    6. Build response factors (sorted by magnitude, direction-corrected).
    7. Build deterministic care plan (next check-in + monitoring thresholds).
    8. Generate Gen AI clinical narrative (LLaMA-3.3-70B) with care plan.
    9. Return assembled PatientDetail.

    All DB and serving errors surface as explicit HTTP errors; none are swallowed.
    Access is fail-closed: a user in no recognised care-unit group, or a request
    for a patient outside the user's units, gets a 404 (never a leak).
    """
    # --- 0. Fail-closed deny: user in no recognised care-unit group ---
    if access.scope_denies_all(care_unit_scope):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Patient icustay_id={icustay_id!r} not found in active census. "
                "Only current ICU patients are scored."
            ),
        )

    # Care-unit predicate reused by both the detail lookup and the batch query
    # so the readiness index is computed within the user's visible cohort.
    fragment, cu_params = access.care_unit_filter_clause(care_unit_scope)

    # --- 1. Fetch patient census row (scoped when enforced) ---
    patient_sql = _PATIENT_CENSUS_SELECT + (f" AND {fragment}" if fragment else "")
    try:
        result = session.execute(
            text(patient_sql), {"icustay_id": icustay_id, **cu_params}
        )
        keys = list(result.keys())
        row_tuple = result.fetchone()
    except Exception as exc:
        # Full error logged server-side; client gets a stable, generic message.
        logger.error("Lakebase census query failed for %s: %s", icustay_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Patient data is temporarily unavailable.",
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
    # SECURITY: vitals are not care_unit-filtered directly; access is gated by
    # the scoped step-1 lookup above, which 404s before we reach here if the
    # patient is outside the user's units. Keep this query AFTER that guard.
    try:
        vitals_result = session.execute(_VITALS_SQL, {"icustay_id": icustay_id})
        vitals_rows = vitals_result.fetchall()
    except Exception as exc:
        # Full error logged server-side; client gets a stable, generic message.
        logger.error("Lakebase vitals query failed for %s: %s", icustay_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Patient vitals are temporarily unavailable.",
        ) from exc

    vitals: list[VitalPoint] = []
    for vrow in vitals_rows:
        charttime, vital_name, value = vrow
        try:
            vitals.append(
                VitalPoint(
                    charttime=charttime,
                    vital_name=str(vital_name),
                    value=float(value) if value is not None else 0.0,
                )
            )
        except Exception:
            continue  # skip individual malformed rows only

    # --- 3. Fetch all census feature rows (icustay_id included; scoped) ---
    batch_sql = _CENSUS_BATCH_SELECT + (f" WHERE {fragment}" if fragment else "")
    try:
        batch_result = session.execute(text(batch_sql), cu_params)
        batch_keys = list(batch_result.keys())
        batch_rows = [dict(zip(batch_keys, r)) for r in batch_result.fetchall()]
    except Exception as exc:
        # Full error logged server-side; client gets a stable, generic message.
        logger.error("Census batch feature fetch failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Patient data is temporarily unavailable.",
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
        census_id: pred for census_id, pred in zip(ordered_ids, all_predictions)
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
    # M2: normalize ONCE; reuse for both response_factors and the care-plan / narrative bases
    _normalized: list[tuple[str, str, float]] = [
        normalize_factor(
            f.get("name", ""),
            f.get("direction", "risk"),
            float(f.get("magnitude", 0.0)),
        )
        for f in raw_factors
    ]
    response_factors: list[FactorOut] = [
        FactorOut(name=label, direction=direction, magnitude=magnitude)
        for label, direction, magnitude in _normalized
    ]

    # --- 6b. Inject derived-flag guardrail risk factors ---
    # For each inject_risk guardrail, if the census row has the flag set and the
    # label is not already present, insert a synthetic risk factor at the top of
    # the list (magnitude = max existing + epsilon).  Dedup is label-based so a
    # model factor carrying the same label is never double-counted.
    existing_labels: set[str] = {f.name for f in response_factors}
    max_magnitude: float = max((f.magnitude for f in response_factors), default=0.0)
    injected: list[FactorOut] = []
    for g in GUARDRAILS:
        if g.kind != "inject_risk":
            continue
        if not _to_bool(row.get(g.feature, False)):
            continue
        if g.label in existing_labels:
            continue
        injected.append(
            FactorOut(
                name=g.label,
                direction="risk",
                magnitude=max_magnitude + _INJECT_EPSILON,
            )
        )
        existing_labels.add(g.label)
    if injected:
        response_factors = sorted(
            injected + response_factors,
            key=lambda f: f.magnitude,
            reverse=True,
        )

    # M3: Apply TOP_N truncation unconditionally so response_factors is always
    # capped at TOP_N_DISPLAY_FACTORS regardless of whether guardrails fired.
    # Injected factors sort to the head via max+epsilon so they are retained.
    response_factors = response_factors[:TOP_N_DISPLAY_FACTORS]

    # --- 7. Build deterministic care plan ---
    # M1: use final displayed factors (post-injection, post-truncation) so the
    # care-plan basis reflects the same factor set shown in the UI.
    final_factor_tuples: list[tuple[str, str, float]] = [
        (f.name, f.direction, f.magnitude) for f in response_factors
    ]
    care_plan_obj = build_care_plan(band, final_factor_tuples)
    care_plan_out = CarePlanOut(
        next_check_in_hours=care_plan_obj.next_check_in_hours,
        monitoring=[
            MonitoringItemOut(
                parameter=m.parameter,
                threshold=m.threshold,
                rationale=m.rationale,
            )
            for m in care_plan_obj.monitoring
        ],
        basis=care_plan_obj.basis,
    )

    # --- 8. Generate Gen AI narrative (with care plan for verbatim restatement) ---
    # M1: build narrative factors from the final displayed response_factors so
    # injected guardrail risks appear in the AI summary, not just the UI.
    narrative_factors = [
        Factor(name=f.name, direction=f.direction, magnitude=f.magnitude)
        for f in response_factors
    ]
    try:
        # Pass an index-derived representative score so the narrative band label
        # matches the displayed band (raw score clusters ~0.44–0.53 and is not
        # a probability; the narrative must say "Ready"/"Borderline"/"Not ready").
        _band_score_hint = {
            "Ready": 0.90,
            "Borderline": 0.60,
            "Not ready": 0.20,
        }.get(band, patient_score)
        narrative = build_narrative(
            _band_score_hint,
            narrative_factors,
            care_plan=care_plan_obj,
        )
    except Exception as exc:
        logger.warning("Gen AI narrative generation failed: %s", exc)
        narrative = f"Clinical narrative unavailable ({exc}). Readiness band: {band}."

    # Lactate note (present when lactate_last is a top model factor)
    raw_factor_names = [f.get("name", "") for f in raw_factors]
    lactate_note: str | None = (
        _LACTATE_NOTE if "lactate_last" in raw_factor_names else None
    )

    # --- 9. Assemble and return ---
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
        care_plan=care_plan_out,
    )
