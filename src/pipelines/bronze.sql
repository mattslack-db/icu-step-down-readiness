-- =============================================================================
-- bronze.sql — Raw ingestion layer (materialized views from Delta Sharing)
-- =============================================================================
-- Source: mimic_iii_src.mimic_iii.* (read-only Delta Sharing catalog)
-- Target: icu_step_down.bronze.*
-- Pattern: Materialized Views (batch) — Delta Sharing does not support CDF.
-- Column names are UPPERCASE as they arrive from MIMIC-III.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- patients
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.patients
AS SELECT * FROM mimic_iii_src.mimic_iii.patients;

-- ---------------------------------------------------------------------------
-- admissions
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.admissions
AS SELECT * FROM mimic_iii_src.mimic_iii.admissions;

-- ---------------------------------------------------------------------------
-- icu_stays
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.icu_stays
AS SELECT * FROM mimic_iii_src.mimic_iii.icu_stays;

-- ---------------------------------------------------------------------------
-- transfers
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.transfers
AS SELECT * FROM mimic_iii_src.mimic_iii.transfers;

-- ---------------------------------------------------------------------------
-- chart_events — SCOPED to vital-sign + GCS itemids ONLY.
--
-- Decision rationale: chart_events contains ~330M rows total. Ingesting all
-- rows would be expensive and is unnecessary for this use case. We filter to
-- the vital-sign and GCS itemids needed for silver.vital_signs.
--
-- Itemid scope (both CareVue <220000 and MetaVision >=220000):
--   Heart rate:        211, 220045
--   Systolic BP:       51, 442, 455, 6701, 220179, 220050
--   Diastolic BP:      8368, 8440, 8441, 8555, 220180, 220051
--   SpO2:              646, 220277
--   Temperature (F):   678, 223761
--   Temperature (C):   676, 223762
--   Respiratory rate:  615, 618, 220210, 224690
--   GCS (CareVue total): 198
--   GCS (MetaVision components — Eye: 220739, Verbal: 223900, Motor: 223901)
--     Note: MetaVision records GCS as three components; 220739 is Eye Opening.
--     Silver layer uses all three components and sums them for a total.
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.chart_events
AS SELECT *
FROM mimic_iii_src.mimic_iii.chart_events
WHERE ITEMID IN (
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
  -- GCS MetaVision components (Eye, Verbal, Motor)
  220739, 223900, 223901
);

-- ---------------------------------------------------------------------------
-- lab_events
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.lab_events
AS SELECT * FROM mimic_iii_src.mimic_iii.lab_events;

-- ---------------------------------------------------------------------------
-- d_labitems
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.d_labitems
AS SELECT * FROM mimic_iii_src.mimic_iii.d_labitems;

-- ---------------------------------------------------------------------------
-- prescriptions
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.prescriptions
AS SELECT * FROM mimic_iii_src.mimic_iii.prescriptions;

-- ---------------------------------------------------------------------------
-- input_events_cv  (CareVue inputs — vasopressors, fluids)
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.input_events_cv
AS SELECT * FROM mimic_iii_src.mimic_iii.input_events_cv;

-- ---------------------------------------------------------------------------
-- input_events_mv  (MetaVision inputs — vasopressors, fluids)
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.input_events_mv
AS SELECT * FROM mimic_iii_src.mimic_iii.input_events_mv;

-- ---------------------------------------------------------------------------
-- procedure_events_mv  (MetaVision procedures — ventilator events)
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.procedure_events_mv
AS SELECT * FROM mimic_iii_src.mimic_iii.procedure_events_mv;

-- ---------------------------------------------------------------------------
-- services
-- ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.bronze.services
AS SELECT * FROM mimic_iii_src.mimic_iii.services;
