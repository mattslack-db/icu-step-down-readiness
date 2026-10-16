"""Pull all ICU stays with v6-style outcome labels + cohort flags + candidate new features to local parquet (read-only).

Usage: uv run --with databricks-sql-connector --with databricks-sdk --with pyarrow --with pandas \\
           python scripts/ml_experiments/pull_cohort_data.py
"""
import warnings
from pathlib import Path

import databricks.sql as sql
from databricks.sdk import WorkspaceClient

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

# Built from gold.patient_features with v6's outcome definition (deaths in the
# ICU included), NOT from gold.readiness_training_set: the pipeline now drops
# in-ICU deaths from that table, and run "A v6 as-is" needs them.
# died_in_icu uses the pipeline's cutoff (src/pipelines/gold.sql).
BASE = """
WITH bounce_back AS (
  SELECT DISTINCT s1.icustay_id
  FROM icu_step_down.silver.icu_stays s1
  JOIN icu_step_down.silver.icu_stays s2
    ON s2.subject_id = s1.subject_id
   AND s2.icustay_id <> s1.icustay_id
   AND s2.intime > s1.outtime
   AND s2.intime <= s1.outtime + INTERVAL 72 HOURS
  WHERE s1.outtime IS NOT NULL
),
outcomes AS (
  SELECT
    si.icustay_id,
    CASE
      WHEN si.outtime IS NULL THEN 'still_in_icu'
      WHEN COALESCE(si.deathtime, p.dod) <= si.outtime + INTERVAL 72 HOURS THEN 'death'
      WHEN bb.icustay_id IS NOT NULL THEN 'bounce_back'
      ELSE 'safe'
    END AS label_reason
  FROM icu_step_down.silver.icu_stays si
  JOIN icu_step_down.silver.patients p ON p.subject_id = si.subject_id
  LEFT JOIN bounce_back bb ON bb.icustay_id = si.icustay_id
)
SELECT pf.*,
  CASE WHEN o.label_reason = 'safe' THEN 1 ELSE 0 END AS readiness_label,
  o.label_reason,
  CASE WHEN si.deathtime <= si.outtime + INTERVAL 1 HOUR THEN 1 ELSE 0 END AS died_in_icu,
  HOUR(si.outtime)                       AS discharge_hour,
  CASE WHEN DAYOFWEEK(si.outtime) IN (1, 7) THEN 1 ELSE 0 END AS discharge_weekend,
  CASE WHEN HOUR(si.outtime) >= 22 OR HOUR(si.outtime) < 7 THEN 1 ELSE 0 END AS discharge_night
FROM icu_step_down.gold.patient_features pf
JOIN outcomes o ON o.icustay_id = pf.icustay_id
JOIN icu_step_down.silver.icu_stays si ON si.icustay_id = pf.icustay_id
LEFT ANTI JOIN icu_step_down.landing.live_cohort lc ON lc.icustay_id = pf.icustay_id
"""

# Trend features over the 24h before outtime: last-6h mean minus the earlier
# 18h mean, plus a per-hour slope across the whole window.
TRENDS = """
WITH w AS (
  SELECT v.icustay_id, v.vital_name, v.value,
         (unix_timestamp(v.charttime) - unix_timestamp(s.outtime)) / 3600.0 AS h
  FROM icu_step_down.silver.vital_signs v
  JOIN icu_step_down.silver.icu_stays s ON s.icustay_id = v.icustay_id
  WHERE s.outtime IS NOT NULL
    AND v.charttime >= s.outtime - INTERVAL 24 HOURS
    AND v.charttime <  s.outtime
    AND v.vital_name IN ('hr', 'sbp', 'rr', 'spo2', 'temp_c', 'gcs')
)
SELECT icustay_id, vital_name,
  AVG(CASE WHEN h >= -6 THEN value END) - AVG(CASE WHEN h < -6 THEN value END) AS delta_6h,
  REGR_SLOPE(value, h) AS slope_24h,
  COUNT(CASE WHEN h >= -6 THEN 1 END) AS n_last6h
FROM w GROUP BY icustay_id, vital_name
"""

# Hours between the last ventilator-mode chart and outtime (time off the vent).
VENT = """
SELECT s.icustay_id,
  (unix_timestamp(s.outtime) - unix_timestamp(MAX(CAST(ce.CHARTTIME AS TIMESTAMP)))) / 3600.0
    AS hours_since_vent
FROM icu_step_down.bronze.chart_events ce
JOIN icu_step_down.silver.icu_stays s ON s.icustay_id = ce.ICUSTAY_ID
WHERE ce.ITEMID IN (720, 722, 223849)
  AND s.outtime IS NOT NULL
  AND CAST(ce.CHARTTIME AS TIMESTAMP) <= s.outtime
GROUP BY s.icustay_id, s.outtime
"""


def main() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ws = WorkspaceClient(profile="icu-sandbox")
        conn = sql.connect(
            server_hostname=ws.config.host.replace("https://", ""),
            http_path="/sql/1.0/warehouses/c2fa8cdc295a849f",
            access_token=ws.config.oauth_token().access_token,
        )
    with conn, conn.cursor() as cur:
        for name, q in {"base": BASE, "trends": TRENDS, "vent": VENT}.items():
            cur.execute(q)
            tbl = cur.fetchall_arrow()
            tbl.to_pandas().to_parquet(OUT / f"{name}.parquet")
            print(f"{name}: {tbl.num_rows:,} rows x {tbl.num_columns} cols")


if __name__ == "__main__":
    main()
