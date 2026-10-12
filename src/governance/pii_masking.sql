-- =============================================================================
-- pii_masking.sql — Unity Catalog column mask for patient identifiers
-- =============================================================================
-- Run BEFORE the Lakeflow pipeline: gold.patient_features, gold.census and
-- gold.readiness_training_set declare `MASK icu_step_down.gold.mask_patient_id`
-- on subject_id and hadm_id in their pipeline schema (src/pipelines/gold.sql),
-- so the function must exist when the pipeline publishes them.
--
-- Behaviour (evaluated per query, for the querying identity):
--   member of icu_admins → raw MIMIC identifier
--   anyone else          → stable pseudonym 'P-' + first 10 hex chars of
--                          SHA-256('icu-step-down|' || id)
-- The pseudonym is deterministic, so joins and "same patient" grouping still
-- work for masked users, but the raw ID is not shown.
--
-- Lakebase: UC rejects synced tables over masked sources ("cannot have both
-- row/column security and online materialized views"), so the pipeline also
-- publishes gold.census_serving / gold.patient_features_serving, which STORE
-- pseudonymize_id(...) output instead of raw IDs (expectation-enforced). Those
-- are what Lakebase syncs — the app and Postgres never hold raw identifiers.
--
-- Limitation (state it if asked): with a salt in the function body and small
-- integer IDs, the pseudonym is display masking, not cryptographic
-- de-identification. Production would key the hash with a secret.
-- =============================================================================

-- Single definition of the pseudonym, shared by the column mask below and by
-- the pipeline's *_serving tables (which store pseudonyms, never raw IDs).
CREATE OR REPLACE FUNCTION icu_step_down.gold.pseudonymize_id(id STRING)
RETURNS STRING
COMMENT 'Deterministic pseudonym for a patient/admission identifier: P- + 10 hex chars of SHA-256.'
RETURN CASE
  WHEN id IS NULL THEN NULL
  ELSE CONCAT('P-', SUBSTR(SHA2(CONCAT('icu-step-down|', id), 256), 1, 10))
END;

CREATE OR REPLACE FUNCTION icu_step_down.gold.mask_patient_id(id STRING)
RETURNS STRING
COMMENT 'Column mask: raw patient/admission ID for icu_admins, deterministic P- pseudonym for everyone else.'
RETURN CASE
  WHEN is_member('icu_admins') THEN id
  ELSE icu_step_down.gold.pseudonymize_id(id)
END;
