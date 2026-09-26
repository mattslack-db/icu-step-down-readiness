"""
ICU Step-Down Readiness — Training Baseline Computation (Phase 4.1).

Computes decile score statistics from the training set, writes them to
gold.readiness_training_baseline, and provides an idempotent live-snapshot
function that appends current census scores to gold.readiness_score_history.

These scripts are executed by the controller (not deployed as a DAB job).
The job entrypoint (run_drift_check in drift_check.py) reads from these tables.

Tables produced:
    gold.readiness_training_baseline
        quantile      DOUBLE      -- 0.0, 0.1, 0.2, ..., 1.0
        score         DOUBLE      -- readiness_score at this quantile
        model_version STRING      -- registered model version used
        computed_at   TIMESTAMP   -- when this row was written

    gold.readiness_score_history
        icustay_id    STRING      -- patient stay identifier
        readiness_score DOUBLE    -- raw model output
        model_version STRING      -- model version at capture time
        captured_at   TIMESTAMP   -- snapshot timestamp (truncated to minute)
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL strings (expressed here; executed at runtime by the controller)
# ---------------------------------------------------------------------------

_CATALOG = "${var.catalog}"  # Databricks bundle variable substitution

BASELINE_TABLE = "gold.readiness_training_baseline"
HISTORY_TABLE = "gold.readiness_score_history"

BASELINE_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {BASELINE_TABLE} (
    quantile      DOUBLE      NOT NULL,
    score         DOUBLE      NOT NULL,
    model_version STRING      NOT NULL,
    computed_at   TIMESTAMP   NOT NULL
)
USING DELTA
"""

HISTORY_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
    icustay_id      STRING      NOT NULL,
    readiness_score DOUBLE      NOT NULL,
    model_version   STRING      NOT NULL,
    captured_at     TIMESTAMP   NOT NULL
)
USING DELTA
PARTITIONED BY (DATE(captured_at))
"""

# ---------------------------------------------------------------------------
# Pure helpers (testable without Databricks)
# ---------------------------------------------------------------------------


def compute_decile_quantiles(
    scores: list[float],
) -> list[tuple[float, float]]:
    """
    Compute decile quantiles (0.0, 0.1, ..., 1.0) from a list of scores.

    Returns a list of (quantile, score) tuples.  Input is not modified.

    Args:
        scores: Raw readiness scores from the training set.

    Returns:
        11 (quantile, score) pairs corresponding to the 0th through 10th decile.
    """
    if not scores:
        raise ValueError("Cannot compute quantiles from an empty score list.")

    sorted_scores = sorted(scores)  # new list; input unchanged
    n = len(sorted_scores)
    result: list[tuple[float, float]] = []

    for i in range(11):  # 0.0, 0.1, ..., 1.0
        q = round(i / 10, 1)
        # Linear interpolation index
        idx_float = q * (n - 1)
        lo = int(math.floor(idx_float))
        hi = min(lo + 1, n - 1)
        frac = idx_float - lo
        score = sorted_scores[lo] * (1.0 - frac) + sorted_scores[hi] * frac
        result.append((q, score))

    return result


# ---------------------------------------------------------------------------
# Databricks I/O (executed by controller; not unit-tested)
# ---------------------------------------------------------------------------


def write_training_baseline(
    model_version: str,
    spark: Any | None = None,
) -> None:  # pragma: no cover
    """
    Score gold.readiness_training_set, compute decile quantiles, and write
    gold.readiness_training_baseline.  Safe to re-run (overwrites old rows).

    Args:
        model_version: Registered model version string (e.g. "2").
        spark:         SparkSession; defaults to the Databricks runtime session.
    """
    if spark is None:
        from databricks.sdk.runtime import spark as _spark  # type: ignore[import-not-found]

        spark = _spark

    # Create table if needed
    spark.sql(BASELINE_TABLE_DDL)

    # Score training set via the registered model (or reuse scored output)
    training_scores_df = spark.sql(
        f"""
        SELECT readiness_score
        FROM   gold.readiness_training_set
        WHERE  readiness_score IS NOT NULL
        ORDER BY readiness_score
        """
    )
    scores: list[float] = [float(r["readiness_score"]) for r in training_scores_df.collect()]

    if not scores:
        raise ValueError(
            "gold.readiness_training_set returned no readiness_score values. "
            "Run the training pipeline before computing the baseline."
        )

    deciles = compute_decile_quantiles(scores)
    now = datetime.now(timezone.utc)

    # Overwrite: delete existing rows for this model_version first (idempotent).
    spark.sql(
        f"DELETE FROM {BASELINE_TABLE} WHERE model_version = '{model_version}'"
    )

    # Insert new decile rows
    rows_sql = ", ".join(
        f"({q}, {score}, '{model_version}', current_timestamp())"
        for q, score in deciles
    )
    spark.sql(f"INSERT INTO {BASELINE_TABLE} VALUES {rows_sql}")

    logger.info(
        "Wrote %d quantile rows to %s for model_version=%s",
        len(deciles),
        BASELINE_TABLE,
        model_version,
    )


def append_live_snapshot(
    model_version: str,
    spark: Any | None = None,
) -> None:  # pragma: no cover
    """
    Idempotently append a current census snapshot to gold.readiness_score_history.

    Snapshots are captured at minute-level granularity.  A double-insert within
    the same minute is a no-op (guarded by the MERGE statement).

    Args:
        model_version: The model version currently serving predictions.
        spark:         SparkSession; defaults to the Databricks runtime session.
    """
    if spark is None:
        from databricks.sdk.runtime import spark as _spark  # type: ignore[import-not-found]

        spark = _spark

    # Create history table if needed
    spark.sql(HISTORY_TABLE_DDL)

    # Idempotent insert: only add rows for the current minute if not present.
    spark.sql(
        f"""
        MERGE INTO {HISTORY_TABLE} AS tgt
        USING (
            SELECT
                icustay_id,
                readiness_score,
                '{model_version}'                              AS model_version,
                date_trunc('minute', current_timestamp())      AS captured_at
            FROM mimic_iii.census
            WHERE readiness_score IS NOT NULL
        ) AS src
        ON  tgt.icustay_id    = src.icustay_id
        AND tgt.captured_at   = src.captured_at
        WHEN NOT MATCHED THEN INSERT *
        """
    )

    logger.info("Appended live snapshot to %s for model_version=%s", HISTORY_TABLE, model_version)


# ---------------------------------------------------------------------------
# CLI entry point (controller calls this directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import sys

    logging.basicConfig(level=logging.INFO)
    version = sys.argv[1] if len(sys.argv) > 1 else "2"
    write_training_baseline(model_version=version)
    append_live_snapshot(model_version=version)
