"""
ICU Step-Down Readiness — Model Drift Detection (Phase 4.2).

Provides pure metric functions for Population Stability Index (PSI) and
Kolmogorov-Smirnov (KS) statistic, a drift_verdict classifier, and
a job entrypoint (run_drift_check) that reads from Databricks tables and
writes drift metrics to gold.readiness_drift.

Thresholds (documented here as the canonical reference):
    MIN_LIVE_SAMPLE = 30   — minimum live scores needed before reporting drift
    PSI < 0.10             — stable
    PSI < 0.25             — moderate shift
    PSI >= 0.25            — drift

The job entrypoint RAISES (fail-loud) when:
    1. The baseline table is empty (run baseline.py first).
    2. The baseline model_version differs from the served model version
       (re-run baseline.py to rebuild against the current model).

Usage (Databricks job task):
    python -m src.monitoring.drift_check
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_LIVE_SAMPLE: int = 30
"""Minimum live-score sample size before drift metrics are meaningful."""

_PSI_STABLE_THRESHOLD: float = 0.10
_PSI_MODERATE_THRESHOLD: float = 0.25
_EPSILON: float = 1e-10
"""Small constant added to empty bins to prevent log(0) and division by zero."""


# ---------------------------------------------------------------------------
# Pure metric functions
# ---------------------------------------------------------------------------


def population_stability_index(
    baseline: list[float],
    live: list[float],
    bins: int = 10,
) -> float:
    """
    Compute the Population Stability Index (PSI) between two score distributions.

    PSI = Σ (P_live_i − P_base_i) × ln(P_live_i / P_base_i)

    Bin edges are derived from the baseline quantiles so that each baseline
    bin holds an equal share of the baseline population.  This makes PSI = 0
    for identical distributions without requiring epsilon correction on
    non-empty bins.

    Empty live bins receive a tiny epsilon to avoid log(0) / division by zero
    without distorting the metric significantly.

    Args:
        baseline: Training-era readiness scores (immutable — not modified).
        live:     Recent live readiness scores (immutable — not modified).
        bins:     Number of bins (default 10).

    Returns:
        PSI value ≥ 0.  ~0 for identical distributions; grows with shift.
    """
    n_base = len(baseline)
    n_live = len(live)

    # Build bin edges from baseline quantiles (never mutate the input).
    sorted_base = sorted(baseline)

    # Edge at quantile i/bins — produces equally-populated baseline bins.
    edges: list[float] = []
    for i in range(bins + 1):
        idx = min(int(i * n_base / bins), n_base - 1)
        edges.append(sorted_base[idx])

    # Extend to (-inf, +inf) so every value is captured in exactly one bin.
    edges[0] = float("-inf")
    edges[-1] = float("inf")

    # Count values falling into each bin (linear scan; inputs are not modified).
    def _bin_counts(values: list[float]) -> list[int]:
        counts = [0] * bins
        for v in values:
            for i in range(bins):
                if edges[i] <= v < edges[i + 1]:
                    counts[i] += 1
                    break
        return counts

    base_counts = _bin_counts(sorted_base)
    live_counts = _bin_counts(list(live))  # copy reference, not mutated

    # Compute PSI.
    psi = 0.0
    for bc, lc in zip(base_counts, live_counts):
        p_base = bc / n_base if bc > 0 else _EPSILON
        p_live = lc / n_live if lc > 0 else _EPSILON
        psi += (p_live - p_base) * math.log(p_live / p_base)

    return psi


def ks_statistic(baseline: list[float], live: list[float]) -> float:
    """
    Compute the Kolmogorov-Smirnov (KS) statistic between two samples.

    Returns the maximum absolute difference between the two empirical CDFs.
    KS = 0 for identical distributions; KS = 1 for non-overlapping distributions.

    Args:
        baseline: Reference score distribution (immutable — not modified).
        live:     Live score distribution (immutable — not modified).

    Returns:
        KS statistic in [0, 1].
    """
    sorted_base = sorted(baseline)
    sorted_live = sorted(live)
    n_base = len(sorted_base)
    n_live = len(sorted_live)

    # Evaluate both empirical CDFs at every observed value.
    all_points = sorted(set(sorted_base + sorted_live))

    # Binary search helper for CDF(x) = fraction of values <= x.
    def _cdf(sorted_vals: list[float], n: int, x: float) -> float:
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if sorted_vals[mid] <= x:
                lo = mid + 1
            else:
                hi = mid
        return lo / n

    max_gap = 0.0
    for point in all_points:
        gap = abs(_cdf(sorted_base, n_base, point) - _cdf(sorted_live, n_live, point))
        if gap > max_gap:
            max_gap = gap

    return max_gap


def drift_verdict(psi: float, n_live: int) -> str:
    """
    Classify drift severity from PSI and live-sample size.

    Returns one of: "insufficient", "stable", "moderate", "drift".

    Rules:
        n_live < MIN_LIVE_SAMPLE  → "insufficient" (census too small for reliable stats)
        PSI < 0.10                → "stable"
        PSI < 0.25                → "moderate"
        PSI >= 0.25               → "drift"

    Args:
        psi:    Population Stability Index (from population_stability_index).
        n_live: Number of live scores used for the comparison.

    Returns:
        Verdict string.
    """
    if n_live < MIN_LIVE_SAMPLE:
        return "insufficient"
    if psi < _PSI_STABLE_THRESHOLD:
        return "stable"
    if psi < _PSI_MODERATE_THRESHOLD:
        return "moderate"
    return "drift"


# ---------------------------------------------------------------------------
# Job entrypoint (fail-loud guards + Databricks I/O)
# ---------------------------------------------------------------------------


def run_drift_check(
    baseline_reader: Callable[[], dict[str, Any]] | None = None,
    live_reader: Callable[[], list[float]] | None = None,
    served_version: str | None = None,
    writer: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    Orchestrate a single drift-check run.

    This function is the testable core of the job entrypoint.  Callers inject
    readers and writers so the pure logic can be tested without Databricks.

    Fail-loud guards (both raise ValueError):
        1. baseline_reader() returns empty scores.
        2. baseline model_version != served_version.

    Args:
        baseline_reader: Callable returning
            {"scores": list[float], "model_version": str}.
            Defaults to the Databricks table reader.
        live_reader: Callable returning a list[float] of recent live scores.
            Defaults to the Databricks table reader.
        served_version: The model version currently served (string).
            Defaults to the value from the Databricks model-serving endpoint.
        writer: Callable that persists the result dict to gold.readiness_drift.
            Defaults to the Databricks table writer.

    Returns:
        Result dict with keys: psi, ks, verdict, n_live, model_version,
        computed_at.
    """
    if baseline_reader is None:
        baseline_reader = _databricks_baseline_reader
    if live_reader is None:
        live_reader = _databricks_live_reader
    if served_version is None:
        served_version = _get_served_model_version()
    if writer is None:
        writer = _databricks_drift_writer

    # --- Load baseline (fail-loud) -----------------------------------------
    baseline_data = baseline_reader()
    baseline_scores: list[float] = baseline_data.get("scores", [])
    baseline_version: str = baseline_data.get("model_version", "")

    if not baseline_scores:
        raise ValueError(
            "Baseline table is empty — run baseline.py first to populate "
            "gold.readiness_training_baseline before running drift checks."
        )

    if baseline_version != served_version:
        raise ValueError(
            f"Baseline model_version {baseline_version!r} does not match "
            f"served model version {served_version!r}. "
            "Re-run baseline.py to rebuild the baseline against the current model "
            "before comparing distributions."
        )

    # --- Load live scores --------------------------------------------------
    live_scores: list[float] = live_reader()
    n_live = len(live_scores)

    # --- Compute metrics ---------------------------------------------------
    psi = population_stability_index(baseline_scores, live_scores)
    ks = ks_statistic(baseline_scores, live_scores) if n_live > 0 else 0.0
    verdict = drift_verdict(psi, n_live)

    result: dict[str, Any] = {
        "psi": psi,
        "ks": ks,
        "verdict": verdict,
        "n_live": n_live,
        "model_version": served_version,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "Drift check complete: PSI=%.4f  KS=%.4f  verdict=%s  n_live=%d",
        psi,
        ks,
        verdict,
        n_live,
    )

    writer(result)
    return result


# ---------------------------------------------------------------------------
# Default Databricks I/O helpers (used only in the live job, not in tests)
# ---------------------------------------------------------------------------

_CATALOG = "icu_step_down"
"""Unity Catalog name — single source of truth for this module."""

_BASELINE_TABLE = f"{_CATALOG}.gold.readiness_training_baseline"
_HISTORY_TABLE = f"{_CATALOG}.gold.readiness_score_history"
_DRIFT_TABLE = f"{_CATALOG}.gold.readiness_drift"

# DDL for gold.readiness_drift (created by the job on first run if absent).
_DRIFT_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {_DRIFT_TABLE} (
    metric        STRING      NOT NULL,
    value         DOUBLE      NOT NULL,
    verdict       STRING      NOT NULL,
    n_live        INT         NOT NULL,
    model_version STRING      NOT NULL,
    computed_at   TIMESTAMP   NOT NULL
)
USING DELTA
"""


def _databricks_baseline_reader() -> dict[str, Any]:  # pragma: no cover
    """Read training-baseline scores from gold.readiness_training_baseline."""
    from databricks.sdk.runtime import spark  # type: ignore[import-not-found]

    rows = spark.sql(  # noqa: E501
        f"SELECT score, model_version FROM {_BASELINE_TABLE} ORDER BY quantile"
    ).collect()
    if not rows:
        return {"scores": [], "model_version": ""}
    scores = [float(r["score"]) for r in rows]
    model_version = str(rows[0]["model_version"])
    return {"scores": scores, "model_version": model_version}


def _databricks_live_reader() -> list[float]:  # pragma: no cover
    """Read recent live readiness scores from gold.readiness_score_history."""
    from databricks.sdk.runtime import spark  # type: ignore[import-not-found]

    rows = spark.sql(
        f"SELECT readiness_score FROM {_HISTORY_TABLE} "
        "WHERE captured_at >= current_timestamp() - INTERVAL 24 HOURS"
    ).collect()
    return [float(r["readiness_score"]) for r in rows]


def _get_served_model_version() -> str:  # pragma: no cover
    """Return the model version string from the icu-readiness serving endpoint."""
    from databricks.sdk import WorkspaceClient  # type: ignore[import-not-found]

    client = WorkspaceClient()
    endpoint = client.serving_endpoints.get("icu-readiness")
    routes = endpoint.config.traffic_config.routes
    # Take the first (and typically only) route's served_model_name.
    served_model_name: str = routes[0].served_model_name
    # served_model_name is e.g. "readiness_model-2" — extract trailing version.
    return served_model_name.rsplit("-", 1)[-1]


def _databricks_drift_writer(result: dict[str, Any]) -> None:  # pragma: no cover
    """Append PSI and KS rows to gold.readiness_drift.

    After writing, the Lakebase-synced copy (mimic_iii.readiness_drift) is NOT
    refreshed on-demand from here. The SNAPSHOT synced table pipeline refreshes on
    its own schedule. Until the next sync cycle completes, the Lakebase Postgres
    copy may reflect the previous run's metrics. Typical freshness lag equals one
    sync interval as configured on the synced table pipeline (see
    src/lakebase/sync_tables.py, SYNCED_TABLES entry for readiness_drift).
    """
    from databricks.sdk.runtime import spark  # type: ignore[import-not-found]

    spark.sql(_DRIFT_TABLE_DDL)
    spark.sql(
        f"INSERT INTO {_DRIFT_TABLE} VALUES "
        f"('PSI', {result['psi']}, '{result['verdict']}', "
        f"{result['n_live']}, '{result['model_version']}', current_timestamp()), "
        f"('KS',  {result['ks']},  '{result['verdict']}', "
        f"{result['n_live']}, '{result['model_version']}', current_timestamp())"
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    run_drift_check()
