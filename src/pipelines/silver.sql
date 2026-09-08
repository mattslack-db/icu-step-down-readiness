-- =============================================================================
-- silver.sql — Cleaned, typed layer
-- =============================================================================
-- Source: icu_step_down.bronze.*
-- Target: icu_step_down.silver.*
-- All column names from MIMIC-III are UPPERCASE; silver outputs use lowercase.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- silver.patients — typed demographics
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.silver.patients
AS
SELECT
  SUBJECT_ID        AS subject_id,
  GENDER            AS gender,
  CAST(DOB AS TIMESTAMP)  AS dob,
  CAST(DOD AS TIMESTAMP)  AS dod,
  EXPIRE_FLAG       AS expire_flag
FROM icu_step_down.bronze.patients;

-- ---------------------------------------------------------------------------
-- silver.icu_stays — typed ICU stays
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.silver.icu_stays
AS
SELECT
  ICUSTAY_ID        AS icustay_id,
  SUBJECT_ID        AS subject_id,
  HADM_ID           AS hadm_id,
  CAST(INTIME  AS TIMESTAMP) AS intime,
  CAST(OUTTIME AS TIMESTAMP) AS outtime,
  LOS               AS los,
  FIRST_CAREUNIT    AS first_careunit,
  LAST_CAREUNIT     AS last_careunit
FROM icu_step_down.bronze.icu_stays;

-- ---------------------------------------------------------------------------
-- silver.vital_signs — cleaned vitals from bronze.chart_events
--
-- Mapping:
--   hr     — Heart rate (211 CareVue, 220045 MetaVision)
--   sbp    — Systolic BP
--   dbp    — Diastolic BP
--   spo2   — SpO2 / oxygen saturation
--   temp_c — Temperature in Celsius (F values converted: (F-32)*5/9)
--   rr     — Respiratory rate
--   gcs    — GCS value:
--            CareVue 198 = total score directly
--            MetaVision: Eye(220739) + Verbal(223900) + Motor(223901) individually;
--            these are kept as separate rows with vital_name='gcs_component'
--            and aggregated to gcs_total in gold via MAX(gcs) per icustay window.
--            For simplicity in this pipeline, MetaVision GCS components are
--            labelled 'gcs' individually and gold sums appropriately.
--
-- Physiological plausibility filters applied:
--   HR: 20–250 bpm
--   SBP: 50–300 mmHg
--   DBP: 20–200 mmHg
--   SpO2: 50–100 %
--   Temp (Celsius): 30–43 °C
--   RR: 4–60 breaths/min
--   GCS: 1–15 (valid range for components: Eye 1-4, Verbal 1-5, Motor 1-6; total 3-15)
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.silver.vital_signs
AS
WITH mapped AS (
  SELECT
    ICUSTAY_ID                         AS icustay_id,
    SUBJECT_ID                         AS subject_id,
    CAST(CHARTTIME AS TIMESTAMP)       AS charttime,
    ITEMID                             AS itemid,
    VALUENUM                           AS valuenum,
    CASE
      -- Heart rate
      WHEN ITEMID IN (211, 220045)                          THEN 'hr'
      -- Systolic BP
      WHEN ITEMID IN (51, 442, 455, 6701, 220179, 220050)   THEN 'sbp'
      -- Diastolic BP
      WHEN ITEMID IN (8368, 8440, 8441, 8555, 220180, 220051) THEN 'dbp'
      -- SpO2
      WHEN ITEMID IN (646, 220277)                          THEN 'spo2'
      -- Temperature F -> convert to C in value expression
      WHEN ITEMID IN (678, 223761)                          THEN 'temp_c'
      -- Temperature C (already Celsius)
      WHEN ITEMID IN (676, 223762)                          THEN 'temp_c'
      -- Respiratory rate
      WHEN ITEMID IN (615, 618, 220210, 224690)             THEN 'rr'
      -- GCS (CareVue total; MetaVision components stored individually)
      WHEN ITEMID IN (198, 220739, 223900, 223901)          THEN 'gcs'
    END AS vital_name,
    -- Convert Fahrenheit to Celsius for temp items; keep other values as-is
    CASE
      WHEN ITEMID IN (678, 223761) THEN (VALUENUM - 32.0) * 5.0 / 9.0
      ELSE VALUENUM
    END AS value_cleaned
  FROM icu_step_down.bronze.chart_events
  WHERE VALUENUM IS NOT NULL
    AND ERROR IS NULL
)
SELECT
  icustay_id,
  subject_id,
  charttime,
  vital_name,
  value_cleaned AS value
FROM mapped
WHERE vital_name IS NOT NULL
  AND icustay_id IS NOT NULL
  -- Plausibility filters per vital
  AND (
    (vital_name = 'hr'     AND value_cleaned BETWEEN 20  AND 250)
    OR (vital_name = 'sbp'   AND value_cleaned BETWEEN 50  AND 300)
    OR (vital_name = 'dbp'   AND value_cleaned BETWEEN 20  AND 200)
    OR (vital_name = 'spo2'  AND value_cleaned BETWEEN 50  AND 100)
    OR (vital_name = 'temp_c' AND value_cleaned BETWEEN 30  AND 43)
    OR (vital_name = 'rr'    AND value_cleaned BETWEEN 4   AND 60)
    OR (vital_name = 'gcs'   AND value_cleaned BETWEEN 1   AND 15)
  );

-- ---------------------------------------------------------------------------
-- silver.lab_events — typed labs
-- Lactate itemid 50813 is flagged for convenience (verified: 187,116 rows).
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.silver.lab_events
AS
SELECT
  SUBJECT_ID                        AS subject_id,
  HADM_ID                           AS hadm_id,
  ITEMID                            AS itemid,
  CAST(CHARTTIME AS TIMESTAMP)      AS charttime,
  VALUENUM                          AS valuenum,
  VALUEUOM                          AS valueuom,
  FLAG                              AS flag,
  (ITEMID = 50813)                  AS is_lactate
FROM icu_step_down.bronze.lab_events
WHERE VALUENUM IS NOT NULL;
