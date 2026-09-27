"""
GET /api/analytics — census aggregates for the Analytics & Trends view.

Returns:
  - Readiness band distribution (counts + pct) for the current census
  - Global feature importance (v2 model; top-10 from phase 5A evidence)
  - Average ICU LOS per band
  - Ventilator and vasopressor rates

The band distribution and LOS stats require all census patient scores; we
batch-call the serving endpoint for all 40 patients here.  The global
feature importance is sourced from the v2 SHAP evaluation (evidence/05-ml-metrics.md)
and is static — it reflects the model, not individual census snapshots.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import text

from ..core.dependencies import Dependencies
from ..lib import access
from ..lib.feature_labels import FEATURE_LABELS
from ..lib.readiness import compute_readiness_index, readiness_band_from_index
from ..models import (
    AnalyticsResponse,
    BandCount,
    DriftStatus,
    FeatureImportanceItem,
)
from .census import (
    FEATURE_COLS,
    _build_record,
    _call_serving,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analytics"])

# ---------------------------------------------------------------------------
# Global feature importance from v2 model evaluation (evidence/05-ml-metrics.md).
# Mean |SHAP| values on held-out test set (n=500 sample).
# These are fixed — the model version is pinned.
# ---------------------------------------------------------------------------

_GLOBAL_FEATURE_IMPORTANCE: list[tuple[str, float]] = [
    ("lactate_last", 0.24580),
    ("age", 0.04620),
    ("los", 0.03491),
    ("gcs_last", 0.02956),
    ("spo2_last", 0.02939),
    ("hr_mean", 0.02059),
    ("rr_mean", 0.01490),
    ("hr_last", 0.01404),
    ("sbp_last", 0.01382),
    ("sbp_mean", 0.01293),
]

# Analytics SQL: icustay_id + all FEATURE_COLS (which already include los,
# on_vasopressors, on_ventilator — no duplication). Base SELECT only; a
# care_unit filter is appended per-request when unit-access enforcement is on.
_ANALYTICS_SELECT = (
    'SELECT "icustay_id", '
    + ", ".join(f'"{c}"' for c in FEATURE_COLS)
    + " FROM mimic_iii.census"
)

# Drift SQL: latest PSI row from the Lakebase-synced copy.
# FIX I2: gold.readiness_drift is a UC Delta table; the app's Lakebase
# (Postgres) session only exposes the mimic_iii schema. Querying
# gold.readiness_drift directly from the Postgres session would always fail
# because the 'gold' schema does not exist in Postgres.  The synced table
# mimic_iii.readiness_drift (SNAPSHOT mode, PK=metric) is the correct target.
_DRIFT_PSI_SQL = text(
    "SELECT value, verdict, n_live, model_version, "
    "CAST(computed_at AS VARCHAR) AS computed_at "
    "FROM mimic_iii.readiness_drift "
    "WHERE metric = 'PSI' "
    "ORDER BY computed_at DESC "
    "LIMIT 1"
)

# Drift SQL: latest KS value from the Lakebase-synced copy.
_DRIFT_KS_SQL = text(
    "SELECT value "
    "FROM mimic_iii.readiness_drift "
    "WHERE metric = 'KS' "
    "ORDER BY computed_at DESC "
    "LIMIT 1"
)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    operation_id="getAnalytics",
    summary="Census aggregates: band distribution, feature importance, LOS by band",
)
def get_analytics(
    session: Dependencies.Session,
    ws: Dependencies.Client,
    care_unit_scope: Dependencies.CareUnitScope,
) -> AnalyticsResponse:
    """
    Return aggregate analytics for the current ICU census.

    Steps:
    0. Apply the requesting user's care-unit scope (fail-closed) when enforced.
    1. Query `mimic_iii.census` for all patients + feature columns.
    2. Batch-call `icu-readiness` to get scores for the whole cohort.
    3. Compute relative indices → bands → aggregate stats.
    4. Return aggregates (no individual patient rows).
    """
    # --- 0. Fail-closed deny: user in no recognised care-unit group ---
    # Empty aggregates (HTTP 200) mirror the empty-census path so the UI renders
    # its normal empty state; a denied user never receives patient-derived stats.
    if access.scope_denies_all(care_unit_scope):
        return AnalyticsResponse(
            total_census=0,
            band_distribution=[],
            feature_importance=_feature_importance_items(),
            avg_los_by_band={},
            vent_rate=0.0,
            vasopressor_rate=0.0,
            generated_at=datetime.now(timezone.utc).isoformat(),
            drift_status=None,
        )

    # --- 1. Fetch all census rows (scoped when enforced) ---
    fragment, cu_params = access.care_unit_filter_clause(care_unit_scope)
    analytics_sql = _ANALYTICS_SELECT + (f" WHERE {fragment}" if fragment else "")
    try:
        result = session.execute(text(analytics_sql), cu_params)
        keys = list(result.keys())
        rows: list[dict[str, Any]] = [dict(zip(keys, row)) for row in result.fetchall()]
    except Exception as exc:
        # Full error logged server-side; client gets a stable, generic message.
        logger.error("Lakebase analytics query failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Analytics data is temporarily unavailable.",
        ) from exc

    # --- 1b. Fetch latest drift status (graceful degradation) ---
    drift_status: DriftStatus | None = _fetch_drift_status(session)

    if not rows:
        return AnalyticsResponse(
            total_census=0,
            band_distribution=[],
            feature_importance=_feature_importance_items(),
            avg_los_by_band={},
            vent_rate=0.0,
            vasopressor_rate=0.0,
            generated_at=datetime.now(timezone.utc).isoformat(),
            drift_status=drift_status,
        )

    # --- 2. Batch-call serving ---
    records = [_build_record(row) for row in rows]
    predictions = _call_serving(ws, records)

    # --- 3. Compute indices and bands ---
    raw_scores = [float(p.get("readiness_score", 0.0)) for p in predictions]
    indices = [compute_readiness_index(s, raw_scores) for s in raw_scores]
    bands = [readiness_band_from_index(idx) for idx in indices]

    total = len(rows)

    # Band distribution
    band_counter: dict[str, int] = defaultdict(int)
    for b in bands:
        band_counter[b] += 1

    band_distribution: list[BandCount] = []
    for band_name in ["Ready", "Borderline", "Not ready"]:
        count = band_counter.get(band_name, 0)
        band_distribution.append(
            BandCount(
                band=band_name,
                count=count,
                pct=round(count / total * 100, 1) if total > 0 else 0.0,
            )
        )

    # Average LOS per band
    los_by_band: dict[str, list[float]] = defaultdict(list)
    for row, band in zip(rows, bands):
        los_val = row.get("los")
        if los_val is not None:
            try:
                los_by_band[band].append(float(los_val))
            except (TypeError, ValueError):
                pass

    avg_los_by_band: dict[str, float] = {
        band: round(sum(vals) / len(vals), 2)
        for band, vals in los_by_band.items()
        if vals
    }

    # Vent and vasopressor rates
    vent_count = sum(1 for row in rows if row.get("on_ventilator"))
    vaso_count = sum(1 for row in rows if row.get("on_vasopressors"))
    vent_rate = round(vent_count / total, 4) if total > 0 else 0.0
    vasopressor_rate = round(vaso_count / total, 4) if total > 0 else 0.0

    return AnalyticsResponse(
        total_census=total,
        band_distribution=band_distribution,
        feature_importance=_feature_importance_items(),
        avg_los_by_band=avg_los_by_band,
        vent_rate=vent_rate,
        vasopressor_rate=vasopressor_rate,
        generated_at=datetime.now(timezone.utc).isoformat(),
        drift_status=drift_status,
    )


def _fetch_drift_status(session: Any) -> DriftStatus | None:
    """
    Query the latest PSI and KS rows from gold.readiness_drift.

    Returns None on any error (table not yet created, empty, etc.) so the
    analytics endpoint degrades gracefully when the drift job hasn't run yet.
    KS falls back to None if the KS row is absent (older data or partial write).
    """
    try:
        # --- PSI row (carries verdict, n_live, model_version, computed_at) ---
        psi_result = session.execute(_DRIFT_PSI_SQL)
        psi_row = psi_result.fetchone()
        if psi_row is None:
            return None
        psi_keys = (
            list(psi_result.keys())
            if hasattr(psi_result, "keys")
            else ["value", "verdict", "n_live", "model_version", "computed_at"]
        )
        psi_data = dict(zip(psi_keys, psi_row))

        # --- KS row (optional — graceful fallback to None if absent) ---------
        ks_value: float | None = None
        try:
            ks_result = session.execute(_DRIFT_KS_SQL)
            ks_row = ks_result.fetchone()
            if ks_row is not None:
                ks_value = float(ks_row[0])
        except Exception:
            pass  # KS row absent — leave as None

        return DriftStatus(
            psi=float(psi_data.get("value", 0.0)),
            ks=ks_value,
            verdict=str(psi_data.get("verdict", "insufficient")),
            n_live=int(psi_data.get("n_live", 0)),
            model_version=str(psi_data.get("model_version", "")),
            computed_at=str(psi_data.get("computed_at", "")),
        )
    except Exception as exc:
        logger.info("Drift table not yet available (graceful degradation): %s", exc)
        return None


def _feature_importance_items() -> list[FeatureImportanceItem]:
    """Build human-labelled feature importance list from global constants."""
    return [
        FeatureImportanceItem(
            feature=FEATURE_LABELS.get(raw, raw.replace("_", " ")),
            importance=importance,
        )
        for raw, importance in _GLOBAL_FEATURE_IMPORTANCE
    ]
