-- =============================================================================
-- governance.sql — Unity Catalog governance for icu_step_down catalog
-- Project: ICU Step-Down Readiness
-- Phase:   3 — Unity Catalog Governance
-- Author:  matt.slack@databricks.com
-- Date:    2026-09-08
--
-- Purpose:
--   1. Comments on catalog, schemas, and key tables (idempotent DDL).
--   2. Column-level classification tags on patient identifiers in all three gold tables.
--   3. Broad read grants to `account users` on the gold schema.
--
-- Idempotency: COMMENT ON, SET TAGS, and GRANT are all safe to re-run.
--   - COMMENT ON overwrites; SET TAGS overwrites; GRANT is a no-op if already granted.
--
-- NOTE (Phase 7): The Databricks App's service principal will receive a tighter,
--   app-SP-specific GRANT on gold (and optionally silver) added in Phase 7.
--   The broad `account users` grant here gives any authenticated workspace user
--   read access suitable for ad-hoc exploration and dashboard usage while the
--   app SP grant is not yet created.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- SECTION 1 — Catalog & schema comments
-- ---------------------------------------------------------------------------

COMMENT ON CATALOG icu_step_down IS
  'ICU Step-Down Readiness project. Contains bronze (raw), silver (cleaned), and gold (features + census) layers sourced from MIMIC-III via Delta Sharing.';

COMMENT ON SCHEMA icu_step_down.bronze IS
  'Raw ingested MIMIC-III via Delta Share. Tables are unmodified source data with minimal type enforcement.';

COMMENT ON SCHEMA icu_step_down.silver IS
  'Cleaned and typed clinical tables. Deduplication, NULL handling, and type casting applied to bronze source data.';

COMMENT ON SCHEMA icu_step_down.gold IS
  'Features, training set, and operational census. Derived from silver; ready for ML model training and live operational dashboards.';


-- ---------------------------------------------------------------------------
-- SECTION 2 — Table comments
--
-- WARNING — MATERIALIZED VIEW metadata loss:
--   The three gold tables (patient_features, readiness_training_set, census)
--   are MATERIALIZED VIEWs created by the Lakeflow pipeline. If the pipeline
--   drops and recreates them, ALL COMMENTs and column TAGS on those views are
--   silently lost — Unity Catalog does not persist them through a DROP/CREATE
--   cycle. governance.sql MUST be re-run after any pipeline recreate. It is
--   fully idempotent (COMMENT ON overwrites; SET TAGS overwrites; GRANT is a
--   no-op if already granted), so re-running is always safe.
-- ---------------------------------------------------------------------------

-- Gold layer
COMMENT ON TABLE icu_step_down.gold.patient_features IS
  'One row per ICU stay. Aggregated vital-sign statistics (mean/min/max/last), GCS, vasopressor and ventilator flags, and last lactate. Primary feature set for the step-down readiness classifier.';

COMMENT ON TABLE icu_step_down.gold.readiness_training_set IS
  'Labelled training set for the step-down readiness model. Joins patient_features with icu_stays-derived outcome labels (LOS-based proxy for safe step-down).';

COMMENT ON TABLE icu_step_down.gold.census IS
  'Operational real-time ICU census. One row per currently active ICU stay with live step-down readiness probability (served by the Databricks App in Phase 7).';

-- Silver layer (vital_signs only as required by brief)
COMMENT ON TABLE icu_step_down.silver.vital_signs IS
  'Cleaned vital-sign observations from MIMIC-III chartevents. Outliers capped, timestamps normalised to UTC, and chart items mapped to standard parameter names (hr, sbp, dbp, spo2, temp_c, rr).';


-- ---------------------------------------------------------------------------
-- SECTION 3 — Column classification tags (data governance)
--
-- Tag key: data_classification
-- Tag value: 'pii' — the workspace's tag policy for data_classification permits
--   values [secret, pii, non-pii]. These patient identifiers are classified as pii
--   (even though MIMIC-III is de-identified, the subject/admission/stay IDs are
--   linking keys that must be treated as sensitive in any downstream context).
--
-- Columns tagged on ALL THREE gold tables (same identifiers exist in each):
--   subject_id  — MIMIC-III patient identifier (maps to a real de-identified patient)
--   hadm_id     — Hospital admission identifier (links all events in one admission)
--   icustay_id  — ICU stay identifier (narrower than hadm_id; maps 1:M within admission)
-- ---------------------------------------------------------------------------

-- gold.patient_features
ALTER TABLE icu_step_down.gold.patient_features
  ALTER COLUMN subject_id SET TAGS ('data_classification' = 'pii');

ALTER TABLE icu_step_down.gold.patient_features
  ALTER COLUMN hadm_id SET TAGS ('data_classification' = 'pii');

ALTER TABLE icu_step_down.gold.patient_features
  ALTER COLUMN icustay_id SET TAGS ('data_classification' = 'pii');

-- gold.readiness_training_set
ALTER TABLE icu_step_down.gold.readiness_training_set
  ALTER COLUMN subject_id SET TAGS ('data_classification' = 'pii');

ALTER TABLE icu_step_down.gold.readiness_training_set
  ALTER COLUMN hadm_id SET TAGS ('data_classification' = 'pii');

ALTER TABLE icu_step_down.gold.readiness_training_set
  ALTER COLUMN icustay_id SET TAGS ('data_classification' = 'pii');

-- gold.census
ALTER TABLE icu_step_down.gold.census
  ALTER COLUMN subject_id SET TAGS ('data_classification' = 'pii');

ALTER TABLE icu_step_down.gold.census
  ALTER COLUMN hadm_id SET TAGS ('data_classification' = 'pii');

ALTER TABLE icu_step_down.gold.census
  ALTER COLUMN icustay_id SET TAGS ('data_classification' = 'pii');


-- ---------------------------------------------------------------------------
-- SECTION 4 — Access grants
--
-- Pattern: traversal (USE CATALOG) + schema traversal + data access (SELECT).
-- Grantee: `account users` — every authenticated Databricks account user.
--
-- Rationale:
--   The icu-sandbox workspace is a demo/development environment. Granting
--   `account users` SELECT on gold allows teammates and stakeholders to query
--   the gold tables directly (SQL editor, notebooks) without individual grants.
--
-- Phase 7 note: The Databricks App service principal created in Phase 7 will
--   receive its own GRANT scoped to only the tables the app needs (census +
--   patient_features). That tighter grant complements, and does not replace,
--   this broad grant.
-- ---------------------------------------------------------------------------

-- Catalog traversal
GRANT USE CATALOG ON CATALOG icu_step_down TO `account users`;

-- Gold schema: traversal + read
-- NOTE (production): In production, readiness_training_set should be restricted
--   to the ML pipeline service principal only; SELECT ON SCHEMA here is a sandbox/demo
--   choice that grants all account users access to the full gold layer.
GRANT USE SCHEMA, SELECT ON SCHEMA icu_step_down.gold TO `account users`;
