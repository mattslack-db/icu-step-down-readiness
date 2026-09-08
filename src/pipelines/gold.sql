-- =============================================================================
-- gold.sql — Feature + label + census layer
-- =============================================================================
-- Source: icu_step_down.silver.*  and  icu_step_down.bronze.*
-- Target: icu_step_down.gold.*
-- =============================================================================

-- ---------------------------------------------------------------------------
-- gold.patient_features
--
-- One row per icustay_id. Features computed from the LAST 24 hours of each
-- ICU stay (window: outtime - 24h → outtime; falls back to full stay if < 24h).
--
-- Vital aggregates: mean/min/max/last of hr, sbp, dbp, spo2, temp_c, rr.
-- GCS last: last recorded GCS value in the 24h window.
--
-- on_vasopressors: TRUE if any vasopressor input event in the stay.
--   Vasopressor itemids verified against mimic_iii_src data:
--   MetaVision: norepinephrine=221906, epinephrine=221289, dopamine=221662,
--               dobutamine=221653, vasopressin=222315, phenylephrine=221749
--   CareVue:    norepinephrine=30047/30112, epinephrine=30044/30119,
--               dopamine=30043/30307, dobutamine=30042, vasopressin=30051,
--               phenylephrine=30128
--   Vasopressor window: any time during the stay (not restricted to 24h)
--   because vasopressor use is a stay-level characteristic.
--
-- on_ventilator: TRUE if either:
--   (a) MetaVision: any procedure_events_mv row for the stay with
--       itemid 225792 (Invasive Ventilation), 225794 (Non-Invasive Ventilation),
--       or 224385 (Intubation); OR
--   (b) CareVue / MetaVision mode chart: any chart_events row for the stay with
--       itemid 720 (CareVue Ventilator Mode), 722 (CareVue Ventilator Type),
--       or 223849 (MetaVision Ventilator Mode).
--   The CareVue cohort (~40% of stays) is not captured by procedure_events_mv;
--   the chart_events itemids fill that gap. The combined OR logic covers both eras.
--
-- lactate_last: most recent lactate value (lab_events itemid 50813) in stay.
--
-- age: years at intime = (intime - dob) / 365.25, capped at 90 per MIMIC de-id.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.patient_features
AS
WITH

-- 24-hour window per stay
stay_windows AS (
  SELECT
    icustay_id,
    subject_id,
    hadm_id,
    intime,
    outtime,
    los,
    COALESCE(outtime, intime + INTERVAL 1 DAY) AS window_end,
    COALESCE(outtime, intime + INTERVAL 1 DAY) - INTERVAL 1 DAY AS window_start
  FROM icu_step_down.silver.icu_stays
),

-- Vitals in last 24h window
vitals_window AS (
  SELECT
    sw.icustay_id,
    v.vital_name,
    v.value,
    v.charttime,
    ROW_NUMBER() OVER (
      PARTITION BY sw.icustay_id, v.vital_name
      ORDER BY v.charttime DESC
    ) AS rn
  FROM stay_windows sw
  JOIN icu_step_down.silver.vital_signs v
    ON v.icustay_id = sw.icustay_id
   AND v.charttime >= sw.window_start
   AND v.charttime <  sw.window_end
),

-- Aggregate vitals per stay
vitals_agg AS (
  SELECT
    icustay_id,
    AVG(CASE WHEN vital_name = 'hr'     THEN value END) AS hr_mean,
    MIN(CASE WHEN vital_name = 'hr'     THEN value END) AS hr_min,
    MAX(CASE WHEN vital_name = 'hr'     THEN value END) AS hr_max,
    MAX(CASE WHEN vital_name = 'hr'     AND rn = 1 THEN value END) AS hr_last,
    AVG(CASE WHEN vital_name = 'sbp'    THEN value END) AS sbp_mean,
    MIN(CASE WHEN vital_name = 'sbp'    THEN value END) AS sbp_min,
    MAX(CASE WHEN vital_name = 'sbp'    THEN value END) AS sbp_max,
    MAX(CASE WHEN vital_name = 'sbp'    AND rn = 1 THEN value END) AS sbp_last,
    AVG(CASE WHEN vital_name = 'dbp'    THEN value END) AS dbp_mean,
    MIN(CASE WHEN vital_name = 'dbp'    THEN value END) AS dbp_min,
    MAX(CASE WHEN vital_name = 'dbp'    THEN value END) AS dbp_max,
    MAX(CASE WHEN vital_name = 'dbp'    AND rn = 1 THEN value END) AS dbp_last,
    AVG(CASE WHEN vital_name = 'spo2'   THEN value END) AS spo2_mean,
    MIN(CASE WHEN vital_name = 'spo2'   THEN value END) AS spo2_min,
    MAX(CASE WHEN vital_name = 'spo2'   THEN value END) AS spo2_max,
    MAX(CASE WHEN vital_name = 'spo2'   AND rn = 1 THEN value END) AS spo2_last,
    AVG(CASE WHEN vital_name = 'temp_c' THEN value END) AS temp_c_mean,
    MIN(CASE WHEN vital_name = 'temp_c' THEN value END) AS temp_c_min,
    MAX(CASE WHEN vital_name = 'temp_c' THEN value END) AS temp_c_max,
    MAX(CASE WHEN vital_name = 'temp_c' AND rn = 1 THEN value END) AS temp_c_last,
    AVG(CASE WHEN vital_name = 'rr'     THEN value END) AS rr_mean,
    MIN(CASE WHEN vital_name = 'rr'     THEN value END) AS rr_min,
    MAX(CASE WHEN vital_name = 'rr'     THEN value END) AS rr_max,
    MAX(CASE WHEN vital_name = 'rr'     AND rn = 1 THEN value END) AS rr_last,
    MAX(CASE WHEN vital_name = 'gcs'    AND rn = 1 THEN value END) AS gcs_last
  FROM vitals_window
  GROUP BY icustay_id
),

-- Vasopressor flag: any vasopressor during the ICU stay (MV or CV)
vasopressor_mv AS (
  SELECT DISTINCT ICUSTAY_ID AS icustay_id, TRUE AS on_vasopressors
  FROM icu_step_down.bronze.input_events_mv
  WHERE ITEMID IN (221906, 221289, 221662, 221653, 222315, 221749)
    AND ICUSTAY_ID IS NOT NULL
),
vasopressor_cv AS (
  SELECT DISTINCT ICUSTAY_ID AS icustay_id, TRUE AS on_vasopressors
  FROM icu_step_down.bronze.input_events_cv
  WHERE ITEMID IN (30047, 30112, 30044, 30119, 30043, 30307, 30042, 30051, 30128)
    AND ICUSTAY_ID IS NOT NULL
),
vasopressors AS (
  SELECT icustay_id FROM vasopressor_mv
  UNION
  SELECT icustay_id FROM vasopressor_cv
),

-- Ventilator flag: MetaVision procedure_events_mv (path a)
ventilator_mv_proc AS (
  SELECT DISTINCT ICUSTAY_ID AS icustay_id
  FROM icu_step_down.bronze.procedure_events_mv
  WHERE ITEMID IN (225792, 225794, 224385)
    AND ICUSTAY_ID IS NOT NULL
),
-- Ventilator flag: CareVue + MetaVision mode via chart_events (path b)
ventilator_chart AS (
  SELECT DISTINCT ICUSTAY_ID AS icustay_id
  FROM icu_step_down.bronze.chart_events
  WHERE ITEMID IN (720, 722, 223849)
    AND ICUSTAY_ID IS NOT NULL
),
-- Combined: on_ventilator = TRUE if present in either path
ventilator AS (
  SELECT icustay_id FROM ventilator_mv_proc
  UNION
  SELECT icustay_id FROM ventilator_chart
),

-- Lactate: most recent value during the stay
lactate AS (
  SELECT
    hadm_id,
    LAST_VALUE(valuenum) OVER (
      PARTITION BY hadm_id
      ORDER BY charttime
      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS lactate_last
  FROM icu_step_down.silver.lab_events
  WHERE is_lactate = TRUE
    AND valuenum IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY hadm_id ORDER BY charttime DESC) = 1
)

SELECT
  sw.icustay_id,
  sw.subject_id,
  sw.hadm_id,
  sw.los,
  -- Age capped at 90 per MIMIC de-identification protocol
  LEAST(
    DATEDIFF(sw.intime, p.dob) / 365.25,
    90.0
  )                                          AS age,
  -- Vital aggregates
  va.hr_mean,     va.hr_min,     va.hr_max,     va.hr_last,
  va.sbp_mean,    va.sbp_min,    va.sbp_max,    va.sbp_last,
  va.dbp_mean,    va.dbp_min,    va.dbp_max,    va.dbp_last,
  va.spo2_mean,   va.spo2_min,   va.spo2_max,   va.spo2_last,
  va.temp_c_mean, va.temp_c_min, va.temp_c_max, va.temp_c_last,
  va.rr_mean,     va.rr_min,     va.rr_max,     va.rr_last,
  va.gcs_last,
  -- Vasopressor and ventilator flags
  (vp.icustay_id IS NOT NULL) AS on_vasopressors,
  (vt.icustay_id IS NOT NULL) AS on_ventilator,
  -- Lactate
  lac.lactate_last
FROM stay_windows sw
JOIN icu_step_down.silver.patients p
  ON p.subject_id = sw.subject_id
LEFT JOIN vitals_agg va
  ON va.icustay_id = sw.icustay_id
LEFT JOIN vasopressors vp
  ON vp.icustay_id = sw.icustay_id
LEFT JOIN ventilator vt
  ON vt.icustay_id = sw.icustay_id
LEFT JOIN lactate lac
  ON lac.hadm_id = sw.hadm_id;

-- ---------------------------------------------------------------------------
-- gold.readiness_training_set
--
-- Label proxy (documented):
--   readiness_label = 1  (positive: successful step-down)
--     → stay has OUTTIME IS NOT NULL (patient was discharged from ICU)
--       AND no subsequent ICU stay begins within 72 hours of this stay's outtime
--       (i.e., no bounce-back readmission)
--   readiness_label = 0  (negative: not ready / bounced back)
--     → either OUTTIME IS NULL (still in ICU)
--       OR a subsequent ICU stay exists beginning within 72h of outtime
--
-- Self-join is on subject_id; the 72h window is the standard ICU readmission
-- threshold used in clinical literature for "unplanned readmission."
--
-- Note: MIMIC-III is fully retrospective so nearly all stays have OUTTIME.
-- The label distribution will reflect historical outcomes.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.readiness_training_set
AS
WITH bounce_back AS (
  -- For each ICU stay, find if there is a SUBSEQUENT stay beginning within 72h
  SELECT DISTINCT s1.icustay_id
  FROM icu_step_down.silver.icu_stays s1
  JOIN icu_step_down.silver.icu_stays s2
    ON s2.subject_id = s1.subject_id
   AND s2.icustay_id <> s1.icustay_id
   AND s2.intime > s1.outtime
   AND s2.intime <= s1.outtime + INTERVAL 72 HOURS
  WHERE s1.outtime IS NOT NULL
)
SELECT
  pf.*,
  CASE
    WHEN si.outtime IS NULL        THEN 0  -- Still in ICU
    WHEN bb.icustay_id IS NOT NULL THEN 0  -- Bounced back within 72h
    ELSE                                1  -- Successful step-down
  END AS readiness_label
FROM icu_step_down.gold.patient_features pf
JOIN icu_step_down.silver.icu_stays si
  ON si.icustay_id = pf.icustay_id
LEFT JOIN bounce_back bb
  ON bb.icustay_id = pf.icustay_id;

-- ---------------------------------------------------------------------------
-- gold.census
--
-- "Current" ICU patients for operational scoring.
--
-- MIMIC-III is retrospective; very few stays have outtime IS NULL. Therefore:
-- Decision: use the 40 most recent ICU stays by intime that have POPULATED
-- vital aggregates (hr_mean IS NOT NULL AND spo2_mean IS NOT NULL AND
-- gcs_last IS NOT NULL). This ensures the census always contains stays with
-- rich clinical data for the app's scoring and detail views.
-- 36,518 of 61,532 stays have hr_mean populated; the filter simply skips
-- the small fraction of very-short stays where chart_events were not recorded.
-- (Phase 2 amendment: previously selected most-recent-40 unconditionally,
--  which happened to return 37/40 rows with NULL vital aggregates.)
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.census
AS
WITH recent_stays_with_vitals AS (
  SELECT s.icustay_id
  FROM icu_step_down.silver.icu_stays s
  JOIN icu_step_down.gold.patient_features pf
    ON pf.icustay_id = s.icustay_id
  WHERE pf.hr_mean  IS NOT NULL
    AND pf.spo2_mean IS NOT NULL
    AND pf.gcs_last  IS NOT NULL
  ORDER BY s.intime DESC
  LIMIT 40
)
SELECT pf.*
FROM icu_step_down.gold.patient_features pf
JOIN recent_stays_with_vitals rs
  ON rs.icustay_id = pf.icustay_id;
