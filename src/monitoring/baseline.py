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

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature columns — mirrors src/ml/model.py:FEATURE_COLS exactly.
# Keep in sync with that file when adding or renaming features.
# ---------------------------------------------------------------------------
_FEATURE_COLS: list[str] = [
    "hr_mean", "hr_min", "hr_max", "hr_last",
    "sbp_mean", "sbp_min", "sbp_max", "sbp_last",
    "dbp_mean", "dbp_min", "dbp_max", "dbp_last",
    "spo2_mean", "spo2_min", "spo2_max", "spo2_last",
    "temp_c_mean", "temp_c_min", "temp_c_max", "temp_c_last",
    "rr_mean", "rr_min", "rr_max", "rr_last",
    "on_vasopressors", "on_ventilator",
    "gcs_last", "lactate_last", "los", "age",
]

# ---------------------------------------------------------------------------
# DDL strings (expressed here; executed at runtime by the controller)
# ---------------------------------------------------------------------------

_CATALOG = "icu_step_down"
"""Unity Catalog name — single source of truth for this module."""

BASELINE_TABLE = f"{_CATALOG}.gold.readiness_training_baseline"
HISTORY_TABLE = f"{_CATALOG}.gold.readiness_score_history"
CENSUS_SOURCE = f"{_CATALOG}.gold.census"

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
"""

# ---------------------------------------------------------------------------
# Pure helpers (testable without Databricks)
# ---------------------------------------------------------------------------


def _coerce_feature_frame(df: "pd.DataFrame") -> "pd.DataFrame":
    """
    Return a new DataFrame with boolean feature columns cast to float64.

    MLflow signature enforcement for the readiness model declares
    on_vasopressors and on_ventilator as double (required), but the upstream
    Delta tables (gold.readiness_training_set, gold.census) store them
    as BOOLEAN.  MLflow will NOT auto-cast bool → float64 during signature
    enforcement — the cast must happen before model.predict is called.

    The function is dtype-driven (not hardcoded column names) so it handles
    any boolean column present in the DataFrame, including future additions.
    The input frame is never mutated; a new copy is always returned.

    Args:
        df: Feature DataFrame loaded from a Delta table (may contain bool cols).

    Returns:
        New DataFrame with all bool/boolean columns cast to float64; all
        other columns are unchanged.
    """
    import pandas as pd  # type: ignore[import-not-found]  # noqa: PLC0415

    bool_casts = {
        col: df[col].astype("float64")
        for col in df.columns
        if str(df[col].dtype) in ("bool", "boolean")
    }
    return df.assign(**bool_casts) if bool_casts else df.copy()


def parse_scores(predictions: list[str]) -> list[float]:
    """
    Parse readiness_score values from a list of JSON prediction strings.

    Each string is the JSON output of ReadinessModel.predict:
        {"readiness_score": float, "factors": [...]}

    Returns a new list of floats (input is not modified).

    Args:
        predictions: List of JSON strings from the model's "prediction" column.

    Returns:
        List of readiness_score floats in the same order.
    """
    return [float(json.loads(p)["readiness_score"]) for p in predictions]


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

    # Load the registered model — readiness_score does NOT exist as a column in
    # gold.readiness_training_set; it is computed at serving time.
    import mlflow  # type: ignore[import-not-found]

    model = mlflow.pyfunc.load_model(
        f"models:/{_CATALOG}.ml.readiness_model/{model_version}"
    )

    # Read the 30 feature columns from the training set (no readiness_score column).
    feature_select = ", ".join(f"`{c}`" for c in _FEATURE_COLS)
    training_df = spark.sql(
        f"SELECT {feature_select} FROM {_CATALOG}.gold.readiness_training_set"
    )
    training_pandas = training_df.toPandas()

    if training_pandas.empty:
        raise ValueError(
            f"{_CATALOG}.gold.readiness_training_set returned no rows. "
            "Run the training pipeline before computing the baseline."
        )

    # Score the training set; parse readiness_score out of the JSON prediction column.
    # Filter out None/NaN prediction values before parsing so a null row from the
    # model (e.g. a row with all-NaN features) cannot crash json.loads.
    # Coerce bool columns to float64 BEFORE predict — MLflow signature enforcement
    # declares on_vasopressors/on_ventilator as double and will not auto-cast booleans.
    feature_frame = _coerce_feature_frame(training_pandas[_FEATURE_COLS])
    predictions_df = model.predict(feature_frame)
    preds = [p for p in predictions_df["prediction"] if p is not None]
    scores: list[float] = parse_scores(preds)

    if not scores:
        raise ValueError(
            "Model produced no scores from the training set. "
            "Check that all feature columns are populated."
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

    # Load the registered model — readiness_score does NOT exist as a column in
    # gold.census; it must be computed by scoring the feature columns.
    import mlflow  # type: ignore[import-not-found]
    import pandas as pd  # type: ignore[import-not-found]

    model = mlflow.pyfunc.load_model(
        f"models:/{_CATALOG}.ml.readiness_model/{model_version}"
    )

    # Read icustay_id + feature columns from the governed UC gold census table.
    feature_select = ", ".join(f"`{c}`" for c in _FEATURE_COLS)
    census_df = spark.sql(
        f"SELECT icustay_id, {feature_select} FROM {CENSUS_SOURCE}"
    )
    census_pandas = census_df.toPandas()

    if census_pandas.empty:
        logger.info("No census rows found; skipping live snapshot.")
        return

    # Score the census rows.
    # Filter out None/NaN prediction values before parsing (null-safe guard).
    # Coerce bool columns to float64 BEFORE predict — MLflow signature enforcement
    # declares on_vasopressors/on_ventilator as double and will not auto-cast booleans.
    feature_frame = _coerce_feature_frame(census_pandas[_FEATURE_COLS])
    predictions_df = model.predict(feature_frame)
    preds = [p for p in predictions_df["prediction"] if p is not None]
    scores = parse_scores(preds)

    # Snapshot timestamp truncated to the minute (idempotency guard).
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    scored_pandas = pd.DataFrame(
        {
            "icustay_id": census_pandas["icustay_id"].tolist(),
            "readiness_score": scores,
            "model_version": model_version,
            "captured_at": now,
        }
    )

    # Register as a temp view so MERGE can reference it.
    scored_spark = spark.createDataFrame(scored_pandas)
    scored_spark.createOrReplaceTempView("_live_snapshot_staging")

    # Idempotent insert: only add rows for the current minute if not present.
    spark.sql(
        f"""
        MERGE INTO {HISTORY_TABLE} AS tgt
        USING _live_snapshot_staging AS src
        ON  tgt.icustay_id  = src.icustay_id
        AND tgt.captured_at = src.captured_at
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
