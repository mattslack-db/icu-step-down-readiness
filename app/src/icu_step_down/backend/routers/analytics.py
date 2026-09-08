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
from ..lib.feature_labels import FEATURE_LABELS
from ..lib.readiness import compute_readiness_index, readiness_band_from_index
from ..models import (
    AnalyticsResponse,
    BandCount,
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

# Analytics SQL
_ANALYTICS_SQL = text(
    'SELECT "icustay_id", "los", "on_vasopressors", "on_ventilator", '
    + ", ".join(f'"{c}"' for c in FEATURE_COLS)
    + " FROM mimic_iii.census"
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
) -> AnalyticsResponse:
    """
    Return aggregate analytics for the current ICU census.

    Steps:
    1. Query `mimic_iii.census` for all patients + feature columns.
    2. Batch-call `icu-readiness` to get scores for the whole cohort.
    3. Compute relative indices → bands → aggregate stats.
    4. Return aggregates (no individual patient rows).
    """
    # --- 1. Fetch all census rows ---
    try:
        result = session.execute(_ANALYTICS_SQL)
        keys = list(result.keys())
        rows: list[dict[str, Any]] = [
            dict(zip(keys, row)) for row in result.fetchall()
        ]
    except Exception as exc:
        logger.error("Lakebase analytics query failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to query Lakebase for analytics: {exc}",
        ) from exc

    if not rows:
        return AnalyticsResponse(
            total_census=0,
            band_distribution=[],
            feature_importance=_feature_importance_items(),
            avg_los_by_band={},
            vent_rate=0.0,
            vasopressor_rate=0.0,
            generated_at=datetime.now(timezone.utc).isoformat(),
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
    vent_count = sum(
        1 for row in rows if row.get("on_ventilator")
    )
    vaso_count = sum(
        1 for row in rows if row.get("on_vasopressors")
    )
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
    )


def _feature_importance_items() -> list[FeatureImportanceItem]:
    """Build human-labelled feature importance list from global constants."""
    return [
        FeatureImportanceItem(
            feature=FEATURE_LABELS.get(raw, raw.replace("_", " ")),
            importance=importance,
        )
        for raw, importance in _GLOBAL_FEATURE_IMPORTANCE
    ]
