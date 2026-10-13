-- =============================================================================
-- silver.sql — Cleaned, typed layer
-- =============================================================================
-- Source: icu_step_down.bronze.*
-- Target: icu_step_down.silver.*
-- All column names from MIMIC-III are UPPERCASE; silver outputs use lowercase.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- silver.patients — typed demographics, DATE OF BIRTH REMOVED
--
-- PII obfuscation (HIPAA Safe Harbor, 45 CFR 164.514(b)(2)(i)(C)):
--   DOB is a direct date identifier. It is consumed exactly once — in
--   silver.icu_stays, to derive whole-year age at ICU admission — and is NOT
--   carried into silver.patients or any gold table. gold.pii_audit fails the
--   pipeline if a dob column ever reappears downstream of bronze.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.silver.patients
COMMENT 'Typed demographics. DOB intentionally dropped (HIPAA Safe Harbor); age lives on silver.icu_stays as capped whole years.'
AS
SELECT
  SUBJECT_ID        AS subject_id,
  GENDER            AS gender,
  CAST(DOD AS TIMESTAMP)  AS dod,
  EXPIRE_FLAG       AS expire_flag
FROM icu_step_down.bronze.patients;

-- ---------------------------------------------------------------------------
-- silver.icu_stays — typed ICU stays + admission context + obfuscated age
--
-- age_years: whole years at ICU admission, capped at 90. HIPAA Safe Harbor
--   requires ages over 89 to be aggregated into a single "90 or older"
--   category; MIMIC-III additionally shifts DOB for >89s so raw ages compute
--   to ~300. FLOOR + LEAST implements both. The expectation FAILS the update
--   if any row escapes the cap, so a regression cannot silently publish.
-- deathtime / admission_type / admittime come from admissions and feed the
--   gold label (death within 72h = not a safe step-down) and context features.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.silver.icu_stays (
  CONSTRAINT age_hipaa_cap EXPECT (age_years IS NULL OR age_years <= 90) ON VIOLATION FAIL UPDATE,
  CONSTRAINT age_non_negative EXPECT (age_years IS NULL OR age_years >= 0) ON VIOLATION FAIL UPDATE
)
AS
SELECT
  s.ICUSTAY_ID        AS icustay_id,
  s.SUBJECT_ID        AS subject_id,
  s.HADM_ID           AS hadm_id,
  CAST(s.INTIME  AS TIMESTAMP) AS intime,
  CAST(s.OUTTIME AS TIMESTAMP) AS outtime,
  s.LOS               AS los,
  s.FIRST_CAREUNIT    AS first_careunit,
  s.LAST_CAREUNIT     AS last_careunit,
  CAST(LEAST(FLOOR(DATEDIFF(CAST(s.INTIME AS TIMESTAMP), CAST(p.DOB AS TIMESTAMP)) / 365.25), 90) AS INT)
                      AS age_years,
  CAST(a.ADMITTIME AS TIMESTAMP) AS admittime,
  CAST(a.DEATHTIME AS TIMESTAMP) AS deathtime,
  a.ADMISSION_TYPE    AS admission_type
FROM icu_step_down.bronze.icu_stays s
JOIN icu_step_down.bronze.patients p
  ON p.SUBJECT_ID = s.SUBJECT_ID
LEFT JOIN icu_step_down.bronze.admissions a
  ON a.HADM_ID = s.HADM_ID;

-- ---------------------------------------------------------------------------
-- silver.vital_signs — cleaned vitals from bronze.chart_events
--
-- GCS is unified to a comparable 3–15 total for both database eras:
--   CareVue (itemid 198): records a single GCS total directly → used as-is.
--   MetaVision (itemids 220739=Eye, 223900=Verbal, 223901=Motor): records three
--     separate component rows per charttime. These are grouped by
--     (icustay_id, charttime) and SUMmed to produce a 3–15 total matching
--     the CareVue convention. (Note: MetaVision Verbal 223900 can be 0 for
--     intubated patients; the sum is still the standard clinical total.)
--   Both paths produce vital_name='gcs' with value in 3–15; gold.gcs_last
--   reads this unified column directly.
--
-- Mapping (all other vitals):
--   hr     — Heart rate (211 CareVue, 220045 MetaVision)
--   sbp    — Systolic BP
--   dbp    — Diastolic BP
--   spo2   — SpO2 / oxygen saturation
--   temp_c — Temperature in Celsius (Fahrenheit converted: (F-32)*5/9)
--   rr     — Respiratory rate
--
-- Ventilator-mode itemids (720, 722, 223849) are in bronze.chart_events but
-- are NOT emitted as vital_signs rows — they are consumed by gold.patient_features
-- directly from bronze.chart_events for the on_ventilator flag.
--
-- Physiological plausibility filters applied:
--   HR: 20–250 bpm | SBP: 50–300 mmHg | DBP: 20–200 mmHg
--   SpO2: 50–100 % | Temp (°C): 30–43 | RR: 4–60 breaths/min
--   GCS total: 3–15
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.silver.vital_signs
AS
WITH

-- Non-GCS vitals: straightforward itemid → name mapping
non_gcs AS (
  SELECT
    ICUSTAY_ID                         AS icustay_id,
    SUBJECT_ID                         AS subject_id,
    CAST(CHARTTIME AS TIMESTAMP)       AS charttime,
    CASE
      WHEN ITEMID IN (211, 220045)                              THEN 'hr'
      WHEN ITEMID IN (51, 442, 455, 6701, 220179, 220050)       THEN 'sbp'
      WHEN ITEMID IN (8368, 8440, 8441, 8555, 220180, 220051)   THEN 'dbp'
      WHEN ITEMID IN (646, 220277)                              THEN 'spo2'
      WHEN ITEMID IN (678, 223761, 676, 223762)                 THEN 'temp_c'
      WHEN ITEMID IN (615, 618, 220210, 224690)                 THEN 'rr'
    END AS vital_name,
    CASE
      WHEN ITEMID IN (678, 223761) THEN (VALUENUM - 32.0) * 5.0 / 9.0
      ELSE VALUENUM
    END AS value
  FROM icu_step_down.bronze.chart_events
  WHERE ITEMID NOT IN (198, 220739, 223900, 223901, 720, 722, 223849)
    AND VALUENUM IS NOT NULL
    AND ERROR IS NULL
    AND ICUSTAY_ID IS NOT NULL
),

-- CareVue GCS: itemid 198 is a direct 3–15 total
gcs_carevue AS (
  SELECT
    ICUSTAY_ID                   AS icustay_id,
    SUBJECT_ID                   AS subject_id,
    CAST(CHARTTIME AS TIMESTAMP) AS charttime,
    'gcs'                        AS vital_name,
    VALUENUM                     AS value
  FROM icu_step_down.bronze.chart_events
  WHERE ITEMID = 198
    AND VALUENUM IS NOT NULL
    AND ERROR IS NULL
    AND ICUSTAY_ID IS NOT NULL
),

-- MetaVision GCS: SUM the three component itemids per (icustay_id, charttime)
-- to produce a unified 3–15 total. Only emit the row when all three components
-- are present (HAVING COUNT(DISTINCT ITEMID) = 3) to avoid partial sums from
-- charting lag. If any component is missing at a given charttime the row is
-- dropped rather than producing a misleadingly low total.
gcs_metavision AS (
  SELECT
    ICUSTAY_ID                   AS icustay_id,
    MIN(SUBJECT_ID)              AS subject_id,
    CAST(CHARTTIME AS TIMESTAMP) AS charttime,
    'gcs'                        AS vital_name,
    SUM(VALUENUM)                AS value
  FROM icu_step_down.bronze.chart_events
  WHERE ITEMID IN (220739, 223900, 223901)
    AND VALUENUM IS NOT NULL
    AND ERROR IS NULL
    AND ICUSTAY_ID IS NOT NULL
  GROUP BY ICUSTAY_ID, CHARTTIME
  HAVING COUNT(DISTINCT ITEMID) = 3
)

SELECT icustay_id, subject_id, charttime, vital_name, value
FROM non_gcs
WHERE vital_name IS NOT NULL
  AND (
    (vital_name = 'hr'      AND value BETWEEN 20  AND 250)
    OR (vital_name = 'sbp'  AND value BETWEEN 50  AND 300)
    OR (vital_name = 'dbp'  AND value BETWEEN 20  AND 200)
    OR (vital_name = 'spo2' AND value BETWEEN 50  AND 100)
    OR (vital_name = 'temp_c' AND value BETWEEN 30  AND 43)
    OR (vital_name = 'rr'   AND value BETWEEN 4   AND 60)
  )

UNION ALL

SELECT icustay_id, subject_id, charttime, vital_name, value
FROM gcs_carevue
WHERE value BETWEEN 3 AND 15

UNION ALL

SELECT icustay_id, subject_id, charttime, vital_name, value
FROM gcs_metavision
WHERE value BETWEEN 3 AND 15;

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

-- ---------------------------------------------------------------------------
-- silver.urine_output — urine volume events (mL), both database eras
-- Itemids: the standard MIMIC-III urine-output concept set (CareVue 400xx /
-- 43xxx, MetaVision 2265xx/2274xx). GU irrigant-in (227488) is subtracted
-- as a negative volume, per the MIMIC code repository convention.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.silver.urine_output
AS
SELECT
  ICUSTAY_ID                        AS icustay_id,
  CAST(CHARTTIME AS TIMESTAMP)      AS charttime,
  CASE WHEN ITEMID = 227488 THEN -1 * VALUE ELSE VALUE END AS value_ml
FROM icu_step_down.bronze.output_events
WHERE ICUSTAY_ID IS NOT NULL
  AND VALUE IS NOT NULL
  AND VALUE BETWEEN 0 AND 5000;
