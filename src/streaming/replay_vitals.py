"""
Live-vitals replay — turns static MIMIC-III history into a real-time feed.

MIMIC-III is retrospective, so a continuously streaming pipeline would have
nothing new to process. This job makes the census genuinely "live" without
inventing data:

  1. On first run it freezes the 40 current census stays into
     landing.live_cohort, with each stay's final-24h feature window.
  2. The pipeline's bronze.chart_events history flow HOLDS BACK those stays'
     chart events inside that window (src/pipelines/bronze.sql).
  3. Each run releases the next slice of the held-back events — real MIMIC
     rows, in charttime order — into landing.chart_events_feed, which the
     continuous pipeline streams into bronze.chart_events.
  4. The census features, scores and the app's vitals chart then evolve as
     each patient's final day "happens". When the replay completes, the data
     is identical to the original history.

Run on a schedule (resources/jobs.yml). After releasing, it refreshes the
Lakebase snapshot syncs so the app picks up what the pipeline has processed
(one release of lag — the pipeline processes asynchronously).

Reset: truncate the landing tables AND full-refresh bronze.chart_events
(streaming tables are append-only; released rows stay until a full refresh).
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

REPLAY_WINDOW_HOURS = 24.0
"""Length of the held-back window — matches the gold feature window (last 24h)."""

COHORT_TABLE = "icu_step_down.landing.live_cohort"
FEED_TABLE = "icu_step_down.landing.chart_events_feed"
CLOCK_TABLE = "icu_step_down.landing.replay_clock"
SOURCE_TABLE = "mimic_iii_src.mimic_iii.chart_events"

# Same itemid scope as bronze.chart_events (vitals, GCS, ventilator mode).
CHART_ITEMIDS: tuple[int, ...] = (
    211, 220045,                                  # heart rate
    51, 442, 455, 6701, 220179, 220050,           # systolic BP
    8368, 8440, 8441, 8555, 220180, 220051,       # diastolic BP
    646, 220277,                                  # SpO2
    678, 223761, 676, 223762,                     # temperature F / C
    615, 618, 220210, 224690,                     # respiratory rate
    198, 220739, 223900, 223901,                  # GCS (CareVue total, MV components)
    720, 722, 223849,                             # ventilator mode / type
)

# Lakebase synced tables whose snapshot should refresh after a release.
SYNCED_TABLES: tuple[str, ...] = (
    "icu_step_down_lakebase.mimic_iii.census",
    "icu_step_down_lakebase.mimic_iii.census_vitals",
)


@dataclass(frozen=True)
class ReleasePlan:
    """Half-open slice [start_hours, end_hours) of each stay's held-back window."""

    start_hours: float
    end_hours: float
    is_final: bool


def plan_release(
    hours_released: float | None,
    initial_hours: float,
    step_hours: float,
) -> ReleasePlan | None:
    """Return the next slice to release, or None when the replay is complete.

    Args:
        hours_released: Hours of the window already released (None = never run).
        initial_hours:  Hours released on the first run, so the census starts
                        with some recent data rather than empty windows.
        step_hours:     Hours released on each subsequent run.
    """
    if step_hours <= 0:
        raise ValueError(f"step_hours must be positive, got {step_hours}")
    if not 0 <= initial_hours <= REPLAY_WINDOW_HOURS:
        raise ValueError(
            f"initial_hours must be within [0, {REPLAY_WINDOW_HOURS}], got {initial_hours}"
        )

    start = 0.0 if hours_released is None else float(hours_released)
    if start >= REPLAY_WINDOW_HOURS:
        return None

    increment = initial_hours if hours_released is None else step_hours
    end = min(start + increment, REPLAY_WINDOW_HOURS)
    return ReleasePlan(start_hours=start, end_hours=end, is_final=end >= REPLAY_WINDOW_HOURS)


def _offset(hours: float) -> str:
    return f"c.window_start + make_interval(0, 0, 0, 0, 0, 0, {hours * 3600.0})"


def build_release_sql(plan: ReleasePlan) -> str:
    """INSERT the cohort's source events whose charttime falls inside the slice."""
    itemids = ", ".join(str(i) for i in CHART_ITEMIDS)
    return f"""
INSERT INTO {FEED_TABLE}
SELECT ce.*
FROM {SOURCE_TABLE} ce
JOIN {COHORT_TABLE} c
  ON ce.ICUSTAY_ID = c.icustay_id
WHERE ce.ITEMID IN ({itemids})
  AND CAST(ce.CHARTTIME AS TIMESTAMP) >= {_offset(plan.start_hours)}
  AND CAST(ce.CHARTTIME AS TIMESTAMP) < {_offset(plan.end_hours)}
"""


# ---------------------------------------------------------------------------
# Databricks runtime (not unit-tested: needs Spark + the workspace)
# ---------------------------------------------------------------------------

_LANDING_DDL = (
    "CREATE SCHEMA IF NOT EXISTS icu_step_down.landing "
    "COMMENT 'Live-feed landing zone for the streaming pipeline (replayed MIMIC-III events).'",
    f"CREATE TABLE IF NOT EXISTS {FEED_TABLE} AS SELECT * FROM {SOURCE_TABLE} WHERE 1 = 0",
    f"""CREATE TABLE IF NOT EXISTS {CLOCK_TABLE} (
          hours_released DOUBLE NOT NULL,
          released_at    TIMESTAMP NOT NULL
        )""",
    f"""CREATE TABLE IF NOT EXISTS {COHORT_TABLE} (
          icustay_id   STRING    NOT NULL,
          window_start TIMESTAMP NOT NULL,
          window_end   TIMESTAMP NOT NULL
        )""",
)

# Freeze the current census as the live cohort (first run only). Window
# matches gold.patient_features: the 24h before ICU outtime.
_SEED_COHORT_SQL = f"""
INSERT INTO {COHORT_TABLE}
SELECT c.icustay_id,
       s.outtime - INTERVAL 24 HOURS AS window_start,
       s.outtime                     AS window_end
FROM icu_step_down.gold.census c
JOIN icu_step_down.silver.icu_stays s
  ON s.icustay_id = c.icustay_id
WHERE s.outtime IS NOT NULL
"""


def _refresh_synced_tables() -> None:
    from databricks.sdk import WorkspaceClient  # type: ignore[import-not-found]  # noqa: PLC0415

    w = WorkspaceClient()
    for name in SYNCED_TABLES:
        try:
            synced = w.api_client.do("GET", f"/api/2.0/postgres/synced_tables/{name}")
            pipeline_id = synced.get("status", {}).get("pipeline_id")
            if not pipeline_id:
                logger.warning("No pipeline_id for synced table %s; skipping refresh.", name)
                continue
            w.pipelines.start_update(pipeline_id=pipeline_id)
            logger.info("Triggered snapshot refresh of %s (pipeline %s).", name, pipeline_id)
        except Exception as exc:  # an update already running is fine — it will pick up the data
            logger.warning("Could not refresh synced table %s: %s", name, exc)


def run(initial_hours: float, step_hours: float, refresh_sync: bool, seed_only: bool = False) -> None:
    from databricks.sdk.runtime import spark  # type: ignore[import-not-found]  # noqa: PLC0415

    for ddl in _LANDING_DDL:
        spark.sql(ddl)

    if spark.table(COHORT_TABLE).limit(1).count() == 0:
        spark.sql(_SEED_COHORT_SQL)
        logger.info("Seeded live cohort: %d stays.", spark.table(COHORT_TABLE).count())

    if seed_only:
        # Bootstrap: the cohort must exist before the pipeline's first streaming
        # run so the history flow knows which windows to hold back.
        logger.info("Seed-only run: landing tables and cohort ready; nothing released.")
        return

    last = spark.sql(f"SELECT MAX(hours_released) AS h FROM {CLOCK_TABLE}").collect()[0]["h"]
    plan = plan_release(last, initial_hours=initial_hours, step_hours=step_hours)
    if plan is None:
        logger.info("Replay complete (%.1fh released); nothing to do.", REPLAY_WINDOW_HOURS)
        return

    spark.sql(build_release_sql(plan))
    spark.sql(
        f"INSERT INTO {CLOCK_TABLE} VALUES ({plan.end_hours}, current_timestamp())"
    )
    released = spark.table(FEED_TABLE).count()
    logger.info(
        "Released hours [%.1f, %.1f) of the final 24h for the cohort; feed now %d events%s.",
        plan.start_hours, plan.end_hours, released, " (final release)" if plan.is_final else "",
    )

    if refresh_sync:
        _refresh_synced_tables()


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-hours", type=float, default=12.0)
    parser.add_argument("--step-hours", type=float, default=1.0)
    parser.add_argument("--no-refresh-sync", action="store_true")
    parser.add_argument("--seed-only", action="store_true",
                        help="Create landing tables and freeze the cohort, then exit.")
    args = parser.parse_args()
    run(args.initial_hours, args.step_hours,
        refresh_sync=not args.no_refresh_sync, seed_only=args.seed_only)


if __name__ == "__main__":  # pragma: no cover
    main()
