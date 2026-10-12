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
-- lactate_last: most recent lactate value (lab_events itemid 50813) charted
--   BEFORE window_end. (v3 leakage fix: v2 took the last lactate of the whole
--   hospital admission, which could include results drawn after ICU discharge.)
--
-- age: whole years at ICU admission, capped at 90 — computed in
--   silver.icu_stays.age_years so DOB never reaches gold (HIPAA Safe Harbor).
--
-- v3 features (all observed at or before window_end — no post-decision data):
--   Last-24h labs (last value): creatinine, BUN, WBC, haemoglobin, platelets,
--     bicarbonate, sodium, potassium, glucose.
--   Vital variability: hr/sbp/rr/spo2 standard deviation; n_vital_obs
--     (charting density is itself a severity signal).
--   urine_output_24h (mL), vasopressors_24h, ventilated_24h (active support in
--     the window, vs the stay-level on_vasopressors / on_ventilator flags).
--   Context: prior_icu_stays, is_emergency_admit, hours_admit_to_icu,
--     is_surgical_unit / is_cardiac_unit (real MIMIC first_careunit), is_male.
-- ---------------------------------------------------------------------------
CREATE PRIVATE MATERIALIZED VIEW patient_features_base (
  CONSTRAINT age_hipaa_cap EXPECT (age IS NULL OR age <= 90) ON VIOLATION FAIL UPDATE
)
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
    age_years,
    admittime,
    admission_type,
    first_careunit,
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
    MAX(CASE WHEN vital_name = 'gcs'    AND rn = 1 THEN value END) AS gcs_last,
    STDDEV(CASE WHEN vital_name = 'hr'   THEN value END) AS hr_std,
    STDDEV(CASE WHEN vital_name = 'sbp'  THEN value END) AS sbp_std,
    STDDEV(CASE WHEN vital_name = 'rr'   THEN value END) AS rr_std,
    STDDEV(CASE WHEN vital_name = 'spo2' THEN value END) AS spo2_std,
    COUNT(*)                                             AS n_vital_obs
  FROM vitals_window
  GROUP BY icustay_id
),

-- v3: last value of key labs in the 24h window (joined on hadm_id, bounded by
-- the stay's window so labs from other stays/admission phases are excluded)
labs_named AS (
  SELECT
    sw.icustay_id,
    le.charttime,
    CASE
      WHEN le.itemid = 50912            THEN 'creatinine'
      WHEN le.itemid = 51006            THEN 'bun'
      WHEN le.itemid IN (51301, 51300)  THEN 'wbc'
      WHEN le.itemid IN (51222, 50811)  THEN 'hemoglobin'
      WHEN le.itemid = 51265            THEN 'platelets'
      WHEN le.itemid = 50882            THEN 'bicarbonate'
      WHEN le.itemid = 50983            THEN 'sodium'
      WHEN le.itemid = 50971            THEN 'potassium'
      WHEN le.itemid = 50931            THEN 'glucose'
    END AS lab_name,
    le.valuenum
  FROM stay_windows sw
  JOIN icu_step_down.silver.lab_events le
    ON le.hadm_id = sw.hadm_id
   AND le.charttime >= sw.window_start
   AND le.charttime <  sw.window_end
  WHERE le.itemid IN (50912, 51006, 51301, 51300, 51222, 50811, 51265, 50882, 50983, 50971, 50931)
),
labs_window AS (
  SELECT
    icustay_id,
    lab_name,
    valuenum,
    ROW_NUMBER() OVER (PARTITION BY icustay_id, lab_name ORDER BY charttime DESC) AS rn
  FROM labs_named
),
labs_agg AS (
  SELECT
    icustay_id,
    MAX(CASE WHEN lab_name = 'creatinine'  AND rn = 1 THEN valuenum END) AS creatinine_last,
    MAX(CASE WHEN lab_name = 'bun'         AND rn = 1 THEN valuenum END) AS bun_last,
    MAX(CASE WHEN lab_name = 'wbc'         AND rn = 1 THEN valuenum END) AS wbc_last,
    MAX(CASE WHEN lab_name = 'hemoglobin'  AND rn = 1 THEN valuenum END) AS hemoglobin_last,
    MAX(CASE WHEN lab_name = 'platelets'   AND rn = 1 THEN valuenum END) AS platelets_last,
    MAX(CASE WHEN lab_name = 'bicarbonate' AND rn = 1 THEN valuenum END) AS bicarbonate_last,
    MAX(CASE WHEN lab_name = 'sodium'      AND rn = 1 THEN valuenum END) AS sodium_last,
    MAX(CASE WHEN lab_name = 'potassium'   AND rn = 1 THEN valuenum END) AS potassium_last,
    MAX(CASE WHEN lab_name = 'glucose'     AND rn = 1 THEN valuenum END) AS glucose_last
  FROM labs_window
  GROUP BY icustay_id
),

-- v3: urine output in the 24h window
urine_24h AS (
  SELECT sw.icustay_id, SUM(u.value_ml) AS urine_output_24h
  FROM stay_windows sw
  JOIN icu_step_down.silver.urine_output u
    ON u.icustay_id = sw.icustay_id
   AND u.charttime >= sw.window_start
   AND u.charttime <  sw.window_end
  GROUP BY sw.icustay_id
),

-- v3: vasopressor ACTIVE in the 24h window (MV overlap or CV charted in window)
vasopressor_window AS (
  SELECT DISTINCT sw.icustay_id
  FROM stay_windows sw
  JOIN icu_step_down.bronze.input_events_mv mv
    ON mv.ICUSTAY_ID = sw.icustay_id
  WHERE mv.ITEMID IN (221906, 221289, 221662, 221653, 222315, 221749)
    AND mv.STARTTIME < sw.window_end
    AND (mv.ENDTIME IS NULL OR mv.ENDTIME > sw.window_start)
  UNION
  SELECT DISTINCT sw.icustay_id
  FROM stay_windows sw
  JOIN icu_step_down.bronze.input_events_cv cv
    ON cv.ICUSTAY_ID = sw.icustay_id
  WHERE cv.ITEMID IN (30047, 30112, 30044, 30119, 30043, 30307, 30042, 30051, 30128)
    AND cv.CHARTTIME >= sw.window_start
    AND cv.CHARTTIME <  sw.window_end
),

-- v3: prior ICU stays for the same patient (strictly before this stay)
prior_stays AS (
  SELECT s1.icustay_id, COUNT(s2.icustay_id) AS prior_icu_stays
  FROM icu_step_down.silver.icu_stays s1
  LEFT JOIN icu_step_down.silver.icu_stays s2
    ON s2.subject_id = s1.subject_id
   AND s2.outtime <= s1.intime
   AND s2.icustay_id <> s1.icustay_id
  GROUP BY s1.icustay_id
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

-- Lactate: most recent value charted before the step-down point (window_end).
-- Keyed by icustay_id so a later ICU stay's (or post-discharge) lactate can't leak in.
lactate AS (
  SELECT
    sw.icustay_id,
    le.valuenum AS lactate_last
  FROM stay_windows sw
  JOIN icu_step_down.silver.lab_events le
    ON le.hadm_id = sw.hadm_id
   AND le.charttime < sw.window_end
  WHERE le.is_lactate = TRUE
    AND le.valuenum IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY sw.icustay_id ORDER BY le.charttime DESC) = 1
),

-- ==========================================================================
-- Derived signal: recent_extubation
--
-- TRUE when the stay had ventilator support at any point (on_ventilator = TRUE)
-- but no ventilator event is active or charted within the final 24-hour window.
-- This represents a "vent-off transition" — the patient was extubated within the
-- last 24 h and is now breathing independently, carrying post-extubation risk.
--
-- Source: same itemids as on_ventilator (path a + path b below).
--   Path a — MetaVision procedure_events_mv:
--     225792 Invasive Ventilation, 225794 Non-Invasive Ventilation, 224385 Intubation
--   Path b — CareVue / MetaVision chart_events:
--     720 CareVue Ventilator Mode, 722 CareVue Ventilator Type,
--     223849 MetaVision Ventilator Mode
--
-- For procedure_events_mv we check event overlap with the window:
--   STARTTIME < window_end AND (ENDTIME IS NULL OR ENDTIME > window_start)
-- For chart_events we check CHARTTIME falls within the window.
-- ==========================================================================
ventilator_in_window_mv AS (
  SELECT DISTINCT pem.ICUSTAY_ID AS icustay_id
  FROM icu_step_down.bronze.procedure_events_mv pem
  JOIN stay_windows sw ON sw.icustay_id = pem.ICUSTAY_ID
  WHERE pem.ITEMID IN (225792, 225794, 224385)
    AND pem.ICUSTAY_ID IS NOT NULL
    -- Event overlaps 24h window: started before window ends AND
    -- ended after window starts (ongoing events have ENDTIME = NULL)
    AND pem.STARTTIME  < sw.window_end
    AND (pem.ENDTIME IS NULL OR pem.ENDTIME > sw.window_start)
),
ventilator_in_window_chart AS (
  SELECT DISTINCT ce.ICUSTAY_ID AS icustay_id
  FROM icu_step_down.bronze.chart_events ce
  JOIN stay_windows sw ON sw.icustay_id = ce.ICUSTAY_ID
  WHERE ce.ITEMID IN (720, 722, 223849)
    AND ce.ICUSTAY_ID IS NOT NULL
    AND ce.CHARTTIME >= sw.window_start
    AND ce.CHARTTIME <  sw.window_end
),
ventilator_in_window AS (
  SELECT icustay_id FROM ventilator_in_window_mv
  UNION
  SELECT icustay_id FROM ventilator_in_window_chart
),

-- ==========================================================================
-- Derived signal: active_bleeding
--
-- TRUE when any of the following coagulopathy / haemorrhage proxies fire in
-- the final 24-hour window:
--
--   (a) Haemoglobin drop ≥2 g/dL from first to last reading in the window.
--       Threshold: ≥2 g/dL — standard clinical definition of acute significant
--       blood loss (aligned with transfusion trigger literature).
--       Itemids (verified against d_labitems and silver.lab_events row counts):
--         50811 — Hemoglobin (blood gas panel)   : 89,712 rows
--         51222 — Hemoglobin (CBC)               : 752,277 rows
--       Physiological range filter: 1–25 g/dL to exclude artefact.
--
--   (b) INR > 1.5 (coagulopathy proxy).
--       Threshold: 1.5 — standard critical-care coagulopathy cut-off.
--       Itemid 51237 — INR(PT): 470,853 rows.
--
--   (c) Platelet count < 50k/μL (thrombocytopenic bleeding risk).
--       Threshold: 50k — critical-care transfusion trigger per standard guidelines.
--       Itemid 51265 — Platelet Count: 778,163 rows.
--
-- Join key: hadm_id (silver.lab_events lacks icustay_id; consistent with lactate CTE).
-- ==========================================================================

-- Haemoglobin first and last readings in the 24h window per admission
hb_ranked AS (
  SELECT
    le.hadm_id,
    le.valuenum,
    ROW_NUMBER() OVER (PARTITION BY le.hadm_id ORDER BY le.charttime ASC)  AS rn_asc,
    ROW_NUMBER() OVER (PARTITION BY le.hadm_id ORDER BY le.charttime DESC) AS rn_desc
  FROM icu_step_down.silver.lab_events le
  JOIN stay_windows sw ON sw.hadm_id = le.hadm_id
  WHERE le.itemid IN (50811, 51222)          -- blood-gas Hb + CBC Hb
    AND le.charttime >= sw.window_start
    AND le.charttime <  sw.window_end
    AND le.valuenum BETWEEN 1 AND 25         -- physiological range (g/dL)
),
hb_window AS (
  SELECT
    hadm_id,
    MAX(CASE WHEN rn_asc  = 1 THEN valuenum END) AS hb_first,
    MAX(CASE WHEN rn_desc = 1 THEN valuenum END) AS hb_last
  FROM hb_ranked
  GROUP BY hadm_id
),

-- Coagulopathy: any INR > 1.5 or platelets < 50k in the 24h window
coag_window AS (
  SELECT DISTINCT le.hadm_id
  FROM icu_step_down.silver.lab_events le
  JOIN stay_windows sw ON sw.hadm_id = le.hadm_id
  WHERE le.charttime >= sw.window_start
    AND le.charttime <  sw.window_end
    AND le.valuenum IS NOT NULL
    AND (
      (le.itemid = 51237 AND le.valuenum > 1.5)    -- INR > 1.5
      OR (le.itemid = 51265 AND le.valuenum < 50)  -- Platelets < 50k/μL
    )
)

SELECT
  sw.icustay_id,
  sw.subject_id,
  sw.hadm_id,
  sw.los,
  -- Whole-year age, capped at 90 (HIPAA Safe Harbor) — derived in silver; no DOB in gold
  sw.age_years                               AS age,
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
  lac.lactate_last,
  -- -----------------------------------------------------------------------
  -- v3 features
  -- -----------------------------------------------------------------------
  va.hr_std, va.sbp_std, va.rr_std, va.spo2_std,
  va.n_vital_obs,
  la.creatinine_last, la.bun_last, la.wbc_last, la.hemoglobin_last,
  la.platelets_last, la.bicarbonate_last, la.sodium_last, la.potassium_last,
  la.glucose_last,
  ur.urine_output_24h,
  (vpw.icustay_id IS NOT NULL)                AS vasopressors_24h,
  (viw.icustay_id IS NOT NULL)                AS ventilated_24h,
  COALESCE(ps.prior_icu_stays, 0)             AS prior_icu_stays,
  (sw.admission_type = 'EMERGENCY')           AS is_emergency_admit,
  (UNIX_TIMESTAMP(sw.intime) - UNIX_TIMESTAMP(sw.admittime)) / 3600.0
                                              AS hours_admit_to_icu,
  (sw.first_careunit IN ('SICU', 'TSICU', 'CSRU')) AS is_surgical_unit,
  (sw.first_careunit IN ('CCU', 'CSRU'))      AS is_cardiac_unit,
  (p.gender = 'M')                            AS is_male,
  -- -----------------------------------------------------------------------
  -- Derived guardrail signals (Phase 2)
  -- -----------------------------------------------------------------------
  -- recent_extubation: had vent support in stay but none in final 24h window
  --   → vent-off transition within 24h carries post-extubation reintubation risk
  (vt.icustay_id IS NOT NULL AND viw.icustay_id IS NULL) AS recent_extubation,
  -- active_bleeding: Hb drop ≥2 g/dL in window OR coagulopathy (INR>1.5 / plt<50k)
  (
    (hbw.hb_first IS NOT NULL AND hbw.hb_last IS NOT NULL
     AND (hbw.hb_first - hbw.hb_last) >= 2.0)
    OR cw.hadm_id IS NOT NULL
  ) AS active_bleeding,
  -- -----------------------------------------------------------------------
  -- Synthetic care-unit dimension (Phase 3)
  -- Deterministic assignment from icustay_id modulo 3 so the value is
  -- stable across pipeline re-runs.
  -- NOTE: care_unit is a synthetic demo dimension over de-identified data;
  -- it does NOT reflect the patient's actual physical care unit in MIMIC-III.
  -- -----------------------------------------------------------------------
  CASE pmod(CAST(sw.icustay_id AS BIGINT), 3)
    WHEN 0 THEN 'MICU'
    WHEN 1 THEN 'SICU'
    ELSE        'CCU'
  END AS care_unit
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
  ON lac.icustay_id = sw.icustay_id
LEFT JOIN labs_agg la
  ON la.icustay_id = sw.icustay_id
LEFT JOIN urine_24h ur
  ON ur.icustay_id = sw.icustay_id
LEFT JOIN vasopressor_window vpw
  ON vpw.icustay_id = sw.icustay_id
LEFT JOIN prior_stays ps
  ON ps.icustay_id = sw.icustay_id
LEFT JOIN ventilator_in_window viw
  ON viw.icustay_id = sw.icustay_id
LEFT JOIN hb_window hbw
  ON hbw.hadm_id = sw.hadm_id
LEFT JOIN coag_window cw
  ON cw.hadm_id = sw.hadm_id;

-- ---------------------------------------------------------------------------
-- Column masks on identifiers (PII)
--
-- patient_features_base above is PRIVATE: it exists only inside the pipeline
-- and is never published to Unity Catalog. Every published gold table that
-- carries patient identifiers reads from it and declares
-- `MASK icu_step_down.gold.mask_patient_id` on subject_id and hadm_id
-- (function: src/governance/pii_masking.sql — run before this pipeline).
-- Deriving each published table from the unmasked private base avoids
-- re-masking an already-masked value (the pipeline runs as a non-admin).
-- Masks need the explicit column list, so new features must be added here too.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.patient_features (
  icustay_id STRING,
  subject_id STRING MASK icu_step_down.gold.mask_patient_id,
  hadm_id STRING MASK icu_step_down.gold.mask_patient_id,
  los STRING,
  age INT,
  hr_mean DOUBLE,
  hr_min STRING,
  hr_max STRING,
  hr_last STRING,
  sbp_mean DOUBLE,
  sbp_min STRING,
  sbp_max STRING,
  sbp_last STRING,
  dbp_mean DOUBLE,
  dbp_min STRING,
  dbp_max STRING,
  dbp_last STRING,
  spo2_mean DOUBLE,
  spo2_min STRING,
  spo2_max STRING,
  spo2_last STRING,
  temp_c_mean DOUBLE,
  temp_c_min STRING,
  temp_c_max STRING,
  temp_c_last STRING,
  rr_mean DOUBLE,
  rr_min STRING,
  rr_max STRING,
  rr_last STRING,
  gcs_last STRING,
  on_vasopressors BOOLEAN,
  on_ventilator BOOLEAN,
  lactate_last STRING,
  hr_std DOUBLE,
  sbp_std DOUBLE,
  rr_std DOUBLE,
  spo2_std DOUBLE,
  n_vital_obs BIGINT,
  creatinine_last STRING,
  bun_last STRING,
  wbc_last STRING,
  hemoglobin_last STRING,
  platelets_last STRING,
  bicarbonate_last STRING,
  sodium_last STRING,
  potassium_last STRING,
  glucose_last STRING,
  urine_output_24h DOUBLE,
  vasopressors_24h BOOLEAN,
  ventilated_24h BOOLEAN,
  prior_icu_stays BIGINT,
  is_emergency_admit BOOLEAN,
  hours_admit_to_icu DECIMAL(27,6),
  is_surgical_unit BOOLEAN,
  is_cardiac_unit BOOLEAN,
  is_male BOOLEAN,
  recent_extubation BOOLEAN,
  active_bleeding BOOLEAN,
  care_unit STRING
)
COMMENT 'One row per ICU stay: last-24h features. subject_id/hadm_id are column-masked (raw for icu_admins only); age is whole years capped at 90; no DOB.'
AS SELECT * FROM patient_features_base;

-- ---------------------------------------------------------------------------
-- gold.readiness_training_set
--
-- Label (v3): safe step-down = left the ICU ALIVE and NOT readmitted within 72h.
--   readiness_label = 1  → OUTTIME IS NOT NULL, no subsequent ICU stay within
--       72h of OUTTIME, and no death (in the ICU or within 72h of OUTTIME)
--   readiness_label = 0  → still in ICU, OR bounced back within 72h, OR died
--       in the ICU / within 72h of leaving it
--   label_reason records which rule fired (safe / bounce_back / death /
--   still_in_icu) so evaluation can report readmission-only performance too.
--
-- v2 defect fixed here: deaths left the ICU (OUTTIME set) and were never
-- readmitted, so ~5,274 deaths were labelled "safe step-down" — almost 3x the
-- true negative count. Death time = admissions.DEATHTIME, falling back to
-- patients.DOD (date only) for deaths after hospital discharge.
--
-- Self-join is on subject_id; the 72h window is the standard ICU readmission
-- threshold used in clinical literature for "unplanned readmission."
--
-- Note: MIMIC-III is fully retrospective so nearly all stays have OUTTIME.
-- The label distribution will reflect historical outcomes.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.readiness_training_set (
  icustay_id STRING,
  subject_id STRING MASK icu_step_down.gold.mask_patient_id,
  hadm_id STRING MASK icu_step_down.gold.mask_patient_id,
  los STRING,
  age INT,
  hr_mean DOUBLE,
  hr_min STRING,
  hr_max STRING,
  hr_last STRING,
  sbp_mean DOUBLE,
  sbp_min STRING,
  sbp_max STRING,
  sbp_last STRING,
  dbp_mean DOUBLE,
  dbp_min STRING,
  dbp_max STRING,
  dbp_last STRING,
  spo2_mean DOUBLE,
  spo2_min STRING,
  spo2_max STRING,
  spo2_last STRING,
  temp_c_mean DOUBLE,
  temp_c_min STRING,
  temp_c_max STRING,
  temp_c_last STRING,
  rr_mean DOUBLE,
  rr_min STRING,
  rr_max STRING,
  rr_last STRING,
  gcs_last STRING,
  on_vasopressors BOOLEAN,
  on_ventilator BOOLEAN,
  lactate_last STRING,
  hr_std DOUBLE,
  sbp_std DOUBLE,
  rr_std DOUBLE,
  spo2_std DOUBLE,
  n_vital_obs BIGINT,
  creatinine_last STRING,
  bun_last STRING,
  wbc_last STRING,
  hemoglobin_last STRING,
  platelets_last STRING,
  bicarbonate_last STRING,
  sodium_last STRING,
  potassium_last STRING,
  glucose_last STRING,
  urine_output_24h DOUBLE,
  vasopressors_24h BOOLEAN,
  ventilated_24h BOOLEAN,
  prior_icu_stays BIGINT,
  is_emergency_admit BOOLEAN,
  hours_admit_to_icu DECIMAL(27,6),
  is_surgical_unit BOOLEAN,
  is_cardiac_unit BOOLEAN,
  is_male BOOLEAN,
  recent_extubation BOOLEAN,
  active_bleeding BOOLEAN,
  care_unit STRING,
  readiness_label INT,
  label_reason STRING
)
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
  JOIN icu_step_down.silver.patients p
    ON p.subject_id = si.subject_id
  LEFT JOIN bounce_back bb
    ON bb.icustay_id = si.icustay_id
)
SELECT
  pf.*,
  CASE WHEN o.label_reason = 'safe' THEN 1 ELSE 0 END AS readiness_label,
  o.label_reason
FROM patient_features_base pf
JOIN outcomes o
  ON o.icustay_id = pf.icustay_id
-- Current (live-cohort) patients are scored, never trained on: keeps the
-- census out-of-sample and keeps partially replayed windows out of training.
LEFT ANTI JOIN icu_step_down.landing.live_cohort lc
  ON lc.icustay_id = pf.icustay_id;

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
-- Live mode: once src/streaming/replay_vitals.py has frozen a cohort into
-- landing.live_cohort, the census IS that cohort — membership must not change
-- while their held-back vitals are replayed (early in the replay they have
-- little recent data and would otherwise drop out of the "has vitals" filter).
-- Before a cohort exists, fall back to the 40 most recent stays with vitals.
CREATE PRIVATE MATERIALIZED VIEW census_base
AS
WITH live_cohort AS (
  SELECT icustay_id FROM icu_step_down.landing.live_cohort
),
recent_stays_with_vitals AS (
  SELECT s.icustay_id
  FROM icu_step_down.silver.icu_stays s
  JOIN patient_features_base pf
    ON pf.icustay_id = s.icustay_id
  WHERE pf.hr_mean  IS NOT NULL
    AND pf.spo2_mean IS NOT NULL
    AND pf.gcs_last  IS NOT NULL
  ORDER BY s.intime DESC
  LIMIT 40
),
census_ids AS (
  SELECT icustay_id FROM live_cohort
  UNION ALL
  SELECT icustay_id FROM recent_stays_with_vitals
  WHERE NOT EXISTS (SELECT 1 FROM live_cohort)
)
-- care_unit propagates automatically because census is SELECT pf.* from patient_features.
SELECT pf.*
FROM patient_features_base pf
JOIN census_ids rs
  ON rs.icustay_id = pf.icustay_id;

CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.census (
  icustay_id STRING,
  subject_id STRING MASK icu_step_down.gold.mask_patient_id,
  hadm_id STRING MASK icu_step_down.gold.mask_patient_id,
  los STRING,
  age INT,
  hr_mean DOUBLE,
  hr_min STRING,
  hr_max STRING,
  hr_last STRING,
  sbp_mean DOUBLE,
  sbp_min STRING,
  sbp_max STRING,
  sbp_last STRING,
  dbp_mean DOUBLE,
  dbp_min STRING,
  dbp_max STRING,
  dbp_last STRING,
  spo2_mean DOUBLE,
  spo2_min STRING,
  spo2_max STRING,
  spo2_last STRING,
  temp_c_mean DOUBLE,
  temp_c_min STRING,
  temp_c_max STRING,
  temp_c_last STRING,
  rr_mean DOUBLE,
  rr_min STRING,
  rr_max STRING,
  rr_last STRING,
  gcs_last STRING,
  on_vasopressors BOOLEAN,
  on_ventilator BOOLEAN,
  lactate_last STRING,
  hr_std DOUBLE,
  sbp_std DOUBLE,
  rr_std DOUBLE,
  spo2_std DOUBLE,
  n_vital_obs BIGINT,
  creatinine_last STRING,
  bun_last STRING,
  wbc_last STRING,
  hemoglobin_last STRING,
  platelets_last STRING,
  bicarbonate_last STRING,
  sodium_last STRING,
  potassium_last STRING,
  glucose_last STRING,
  urine_output_24h DOUBLE,
  vasopressors_24h BOOLEAN,
  ventilated_24h BOOLEAN,
  prior_icu_stays BIGINT,
  is_emergency_admit BOOLEAN,
  hours_admit_to_icu DECIMAL(27,6),
  is_surgical_unit BOOLEAN,
  is_cardiac_unit BOOLEAN,
  is_male BOOLEAN,
  recent_extubation BOOLEAN,
  active_bleeding BOOLEAN,
  care_unit STRING
)
COMMENT 'Current ICU census (40 stays). subject_id/hadm_id column-masked (raw for icu_admins only).'
AS SELECT * FROM census_base;

-- ---------------------------------------------------------------------------
-- *_serving — the Lakebase (operational) sources, pseudonymised AT REST
--
-- Unity Catalog will not sync a table that carries column masks, so the
-- app-facing copies store pseudonymize_id(...) output instead of raw IDs.
-- The expectations FAIL the update if a raw identifier ever lands here, so
-- the operational store (Postgres) and the app can never receive one.
-- Same pseudonym function as the mask, so tokens match across SQL, Genie and
-- the app.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.census_serving (
  CONSTRAINT no_raw_subject_id EXPECT (subject_id LIKE 'P-%') ON VIOLATION FAIL UPDATE,
  CONSTRAINT no_raw_hadm_id EXPECT (hadm_id IS NULL OR hadm_id LIKE 'P-%') ON VIOLATION FAIL UPDATE
)
COMMENT 'Lakebase source for the app census: identifiers stored as P- pseudonyms (expectation-enforced).'
AS
SELECT * EXCEPT (subject_id, hadm_id),
  icu_step_down.gold.pseudonymize_id(subject_id) AS subject_id,
  icu_step_down.gold.pseudonymize_id(hadm_id) AS hadm_id
FROM census_base;

CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.patient_features_serving (
  CONSTRAINT no_raw_subject_id EXPECT (subject_id LIKE 'P-%') ON VIOLATION FAIL UPDATE,
  CONSTRAINT no_raw_hadm_id EXPECT (hadm_id IS NULL OR hadm_id LIKE 'P-%') ON VIOLATION FAIL UPDATE
)
COMMENT 'Lakebase source for patient features: identifiers stored as P- pseudonyms (expectation-enforced).'
AS
SELECT * EXCEPT (subject_id, hadm_id),
  icu_step_down.gold.pseudonymize_id(subject_id) AS subject_id,
  icu_step_down.gold.pseudonymize_id(hadm_id) AS hadm_id
FROM patient_features_base;

-- ---------------------------------------------------------------------------
-- gold.census_scores — the live census, scored IN the pipeline
--
-- Each continuous-pipeline update re-scores the 40 census stays through the
-- served model (ai_query → Mosaic AI endpoint `icu-readiness`), so readiness
-- moves as replayed vitals stream in. Same relative index and bands as the app
-- (app/src/icu_step_down/backend/lib/readiness.py): index = % of the census
-- with a strictly lower score; Ready >= 66, Borderline >= 33.
-- Genie answers "who is ready now?" from this table (via
-- census_scores_governed) — never from historical outcome labels.
-- No identifiers beyond icustay_id. Feature list must match src/ml/model.py
-- FEATURE_COLS (enforced by tests/ml/test_feature_parity.py).
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.census_scores
COMMENT 'Live census scored by the served readiness model in the pipeline: score, relative index (0-100) and band.'
AS
WITH scored AS (
  SELECT
    icustay_id,
    care_unit,
    on_vasopressors,
    on_ventilator,
    vasopressors_24h,
    ventilated_24h,
    ai_query(
      'icu-readiness',
      named_struct(
        'hr_mean', CAST(hr_mean AS DOUBLE),
        'hr_min', CAST(hr_min AS DOUBLE),
        'hr_max', CAST(hr_max AS DOUBLE),
        'hr_last', CAST(hr_last AS DOUBLE),
        'sbp_mean', CAST(sbp_mean AS DOUBLE),
        'sbp_min', CAST(sbp_min AS DOUBLE),
        'sbp_max', CAST(sbp_max AS DOUBLE),
        'sbp_last', CAST(sbp_last AS DOUBLE),
        'dbp_mean', CAST(dbp_mean AS DOUBLE),
        'dbp_min', CAST(dbp_min AS DOUBLE),
        'dbp_max', CAST(dbp_max AS DOUBLE),
        'dbp_last', CAST(dbp_last AS DOUBLE),
        'spo2_mean', CAST(spo2_mean AS DOUBLE),
        'spo2_min', CAST(spo2_min AS DOUBLE),
        'spo2_max', CAST(spo2_max AS DOUBLE),
        'spo2_last', CAST(spo2_last AS DOUBLE),
        'temp_c_mean', CAST(temp_c_mean AS DOUBLE),
        'temp_c_min', CAST(temp_c_min AS DOUBLE),
        'temp_c_max', CAST(temp_c_max AS DOUBLE),
        'temp_c_last', CAST(temp_c_last AS DOUBLE),
        'rr_mean', CAST(rr_mean AS DOUBLE),
        'rr_min', CAST(rr_min AS DOUBLE),
        'rr_max', CAST(rr_max AS DOUBLE),
        'rr_last', CAST(rr_last AS DOUBLE),
        'on_vasopressors', CAST(on_vasopressors AS DOUBLE),
        'on_ventilator', CAST(on_ventilator AS DOUBLE),
        'gcs_last', CAST(gcs_last AS DOUBLE),
        'lactate_last', CAST(lactate_last AS DOUBLE),
        'los', CAST(los AS DOUBLE),
        'age', CAST(age AS DOUBLE),
        'hr_std', CAST(hr_std AS DOUBLE),
        'sbp_std', CAST(sbp_std AS DOUBLE),
        'rr_std', CAST(rr_std AS DOUBLE),
        'spo2_std', CAST(spo2_std AS DOUBLE),
        'n_vital_obs', CAST(n_vital_obs AS DOUBLE),
        'creatinine_last', CAST(creatinine_last AS DOUBLE),
        'bun_last', CAST(bun_last AS DOUBLE),
        'wbc_last', CAST(wbc_last AS DOUBLE),
        'hemoglobin_last', CAST(hemoglobin_last AS DOUBLE),
        'platelets_last', CAST(platelets_last AS DOUBLE),
        'bicarbonate_last', CAST(bicarbonate_last AS DOUBLE),
        'sodium_last', CAST(sodium_last AS DOUBLE),
        'potassium_last', CAST(potassium_last AS DOUBLE),
        'glucose_last', CAST(glucose_last AS DOUBLE),
        'urine_output_24h', CAST(urine_output_24h AS DOUBLE),
        'vasopressors_24h', CAST(vasopressors_24h AS DOUBLE),
        'ventilated_24h', CAST(ventilated_24h AS DOUBLE),
        'prior_icu_stays', CAST(prior_icu_stays AS DOUBLE),
        'is_emergency_admit', CAST(is_emergency_admit AS DOUBLE),
        'hours_admit_to_icu', CAST(hours_admit_to_icu AS DOUBLE),
        'is_surgical_unit', CAST(is_surgical_unit AS DOUBLE),
        'is_cardiac_unit', CAST(is_cardiac_unit AS DOUBLE),
        'is_male', CAST(is_male AS DOUBLE)
      ),
      returnType => 'STRING'
    ) AS prediction
  FROM census_base
),
parsed AS (
  SELECT
    icustay_id,
    care_unit,
    on_vasopressors,
    on_ventilator,
    vasopressors_24h,
    ventilated_24h,
    CAST(get_json_object(prediction, '$.readiness_score') AS DOUBLE) AS readiness_score,
    get_json_object(prediction, '$.factors[0].name') AS top_factor,
    get_json_object(prediction, '$.factors[0].direction') AS top_factor_direction
  FROM scored
),
indexed AS (
  SELECT
    *,
    -- BROUND (half-to-even) matches Python's round() in the app: with 40 patients an
    -- index of exactly 32.5 / 65.5 must fall on the same side of a band boundary.
    CAST(BROUND(100.0 * (RANK() OVER (ORDER BY readiness_score) - 1) / COUNT(*) OVER ()) AS INT)
      AS readiness_index
  FROM parsed
)
SELECT
  icustay_id,
  care_unit,
  readiness_score,
  readiness_index,
  -- Safety guardrail (app/src/icu_step_down/backend/lib/guardrails.py): active
  -- vasopressors or ventilation in the last 24h caps the band at Borderline,
  -- whatever the rank. The index itself is unchanged.
  CASE
    WHEN readiness_index >= 66
     AND NOT (COALESCE(vasopressors_24h, FALSE) OR COALESCE(ventilated_24h, FALSE)) THEN 'Ready'
    WHEN readiness_index >= 33 THEN 'Borderline'
    ELSE 'Not ready'
  END AS readiness_band,
  (COALESCE(vasopressors_24h, FALSE) OR COALESCE(ventilated_24h, FALSE)) AS life_support_24h,
  top_factor,
  top_factor_direction,
  on_vasopressors,
  on_ventilator,
  vasopressors_24h,
  ventilated_24h,
  current_timestamp() AS scored_at
FROM indexed;

-- ---------------------------------------------------------------------------
-- gold.census_vitals — vital-sign time series for the census patients only
--
-- Feeds the app's patient-detail vitals chart (via Lakebase). Previously a
-- hand-made CTAS in src/lakebase/sync_tables.py; now pipeline-managed so it
-- refreshes with the census. Data minimisation: no subject_id — the app keys
-- vitals by icustay_id only. row_id is a synthetic PK because
-- (icustay_id, charttime, vital_name) has a few natural duplicates.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.census_vitals
COMMENT 'Vitals for current census stays (app chart). No patient identifiers beyond icustay_id.'
AS
SELECT
  CAST(ROW_NUMBER() OVER (ORDER BY vs.icustay_id, vs.charttime, vs.vital_name) AS BIGINT) AS row_id,
  vs.icustay_id,
  vs.charttime,
  vs.vital_name,
  vs.value
FROM icu_step_down.silver.vital_signs vs
JOIN census_base c
  ON vs.icustay_id = c.icustay_id;

-- ---------------------------------------------------------------------------
-- gold.pii_audit — pipeline-enforced evidence that DOB never leaves bronze
--
-- One row per (schema, column) in silver/gold whose name marks it as a date
-- of birth. The expectation FAILS the pipeline update if any such column
-- exists, so DOB re-entering the curated layers is a hard pipeline failure
-- (visible in the event log), not a review finding. A healthy run publishes
-- a single sentinel row with forbidden_columns = 0.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.pii_audit (
  CONSTRAINT no_dob_in_curated_layers EXPECT (forbidden_columns = 0) ON VIOLATION FAIL UPDATE
)
COMMENT 'PII audit: fails the pipeline if a date-of-birth column appears in silver or gold.'
AS
SELECT
  current_timestamp()                                          AS audited_at,
  COUNT(c.column_name)                                         AS forbidden_columns,
  COALESCE(CONCAT_WS(', ', COLLECT_LIST(CONCAT(c.table_schema, '.', c.table_name, '.', c.column_name))), '')
                                                               AS offending_columns
-- The sentinel reads the final gold tables so the audit is scheduled AFTER
-- every curated table in this update has been (re)published.
FROM (
  SELECT 1 AS one
  FROM (SELECT COUNT(*) AS n FROM icu_step_down.gold.readiness_training_set) t
  CROSS JOIN (SELECT COUNT(*) AS n FROM icu_step_down.gold.census) cn
) sentinel
LEFT JOIN icu_step_down.information_schema.columns c
  ON c.table_schema IN ('silver', 'gold')
 AND LOWER(c.column_name) IN ('dob', 'date_of_birth', 'birth_date', 'birthdate');
