-- =============================================================================
-- bronze.sql — Raw ingestion layer (STREAMING tables)
-- =============================================================================
-- Source: mimic_iii_src.mimic_iii.* (Delta Sharing catalog, shared WITH
--         HISTORY so it can be read as a stream) + the live-feed landing table
-- Target: icu_step_down.bronze.*
-- Pattern: streaming tables — each pipeline update (continuous mode, see
--          resources/pipelines.yml) incrementally ingests only new rows.
-- Column names are UPPERCASE as they arrive from MIMIC-III.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- patients
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.patients
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.patients);

-- ---------------------------------------------------------------------------
-- admissions
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.admissions
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.admissions);

-- ---------------------------------------------------------------------------
-- icu_stays
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.icu_stays
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.icu_stays);

-- ---------------------------------------------------------------------------
-- transfers
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.transfers
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.transfers);

-- ---------------------------------------------------------------------------
-- chart_events — SCOPED to vital-sign, GCS, and ventilator-mode itemids.
--
-- Decision rationale: chart_events contains ~330M rows total. Ingesting all
-- rows would be expensive and is unnecessary for this use case. We filter to
-- the itemids needed for silver.vital_signs and the gold.on_ventilator flag.
--
-- Itemid scope (both CareVue <220000 and MetaVision >=220000):
--   Heart rate:             211, 220045
--   Systolic BP:            51, 442, 455, 6701, 220179, 220050
--   Diastolic BP:           8368, 8440, 8441, 8555, 220180, 220051
--   SpO2:                   646, 220277
--   Temperature (F):        678, 223761
--   Temperature (C):        676, 223762
--   Respiratory rate:       615, 618, 220210, 224690
--   GCS (CareVue total):    198 (direct 3–15 score)
--   GCS (MetaVision Eye):   220739 | GCS Verbal: 223900 | GCS Motor: 223901
--     Silver layer SUMs the three MetaVision components per (icustay_id,charttime)
--     to produce a unified 3–15 total matching the CareVue total.
--   Ventilator (CareVue):   720 (Ventilator Mode), 722 (Ventilator Type)
--   Ventilator (MetaVision): 223849 (Ventilator Mode)
--     These are used for on_ventilator detection for the CareVue cohort; the
--     MetaVision cohort is covered by procedure_events_mv (225792/225794/224385).
-- ---------------------------------------------------------------------------
--
-- Two append flows feed this table:
--   chart_events_history — the shared MIMIC-III history, EXCEPT the final-24h
--     window of each stay in landing.live_cohort (held back for the replay).
--   chart_events_live    — the live feed: src/streaming/replay_vitals.py
--     releases those held-back events, in charttime order, into
--     landing.chart_events_feed, and the continuous pipeline streams them in.
-- The cohort is a static (stream-static) join, read at stream start: it must be
-- seeded before the first run, and changing it needs a full refresh.
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.chart_events
COMMENT 'Vital-sign / GCS / ventilator chart events: shared history + live replay feed.';

CREATE FLOW chart_events_history
AS INSERT INTO icu_step_down.bronze.chart_events BY NAME
SELECT ce.*
FROM STREAM(mimic_iii_src.mimic_iii.chart_events) ce
LEFT JOIN icu_step_down.landing.live_cohort lc
  ON ce.ICUSTAY_ID = lc.icustay_id
 AND CAST(ce.CHARTTIME AS TIMESTAMP) >= lc.window_start
 AND CAST(ce.CHARTTIME AS TIMESTAMP) <  lc.window_end
WHERE lc.icustay_id IS NULL      -- not a held-back live-cohort event
  AND ce.ITEMID IN (
  -- Heart rate
  211, 220045,
  -- Systolic BP
  51, 442, 455, 6701, 220179, 220050,
  -- Diastolic BP
  8368, 8440, 8441, 8555, 220180, 220051,
  -- SpO2
  646, 220277,
  -- Temperature F
  678, 223761,
  -- Temperature C
  676, 223762,
  -- Respiratory rate
  615, 618, 220210, 224690,
  -- GCS CareVue total
  198,
  -- GCS MetaVision components (Eye, Verbal, Motor) — summed to total in silver
  220739, 223900, 223901,
  -- Ventilator mode/type — CareVue cohort ventilator detection
  720, 722,
  -- Ventilator mode — MetaVision (complements procedure_events_mv)
  223849
);

CREATE FLOW chart_events_live
AS INSERT INTO icu_step_down.bronze.chart_events BY NAME
SELECT * FROM STREAM(icu_step_down.landing.chart_events_feed);

-- ---------------------------------------------------------------------------
-- lab_events
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.lab_events
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.lab_events);

-- ---------------------------------------------------------------------------
-- d_labitems
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.d_labitems
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.d_labitems);

-- ---------------------------------------------------------------------------
-- prescriptions
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.prescriptions
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.prescriptions);

-- ---------------------------------------------------------------------------
-- input_events_cv  (CareVue inputs — vasopressors, fluids)
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.input_events_cv
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.input_events_cv);

-- ---------------------------------------------------------------------------
-- input_events_mv  (MetaVision inputs — vasopressors, fluids)
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.input_events_mv
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.input_events_mv);

-- ---------------------------------------------------------------------------
-- procedure_events_mv  (MetaVision procedures — ventilator events)
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.procedure_events_mv
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.procedure_events_mv);

-- ---------------------------------------------------------------------------
-- output_events — SCOPED to urine-output itemids (MIMIC code repository set)
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.output_events
AS SELECT *
FROM STREAM(mimic_iii_src.mimic_iii.output_events)
WHERE ITEMID IN (
  -- CareVue
  40055, 43175, 40069, 40094, 40715, 40473, 40085, 40057, 40056, 40405,
  40428, 40086, 40096, 40651,
  -- MetaVision
  226559, 226560, 226561, 226584, 226563, 226564, 226565, 226567, 226557,
  226558, 227488, 227489
);

-- ---------------------------------------------------------------------------
-- services
-- ---------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE icu_step_down.bronze.services
AS SELECT * FROM STREAM(mimic_iii_src.mimic_iii.services);
