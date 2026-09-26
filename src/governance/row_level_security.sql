-- =============================================================================
-- row_level_security.sql — Unity Catalog row filter for unit-level access control
-- Project: ICU Step-Down Readiness
-- Phase:   3 — Unit-Level Row Access Control
-- Author:  matt.slack@databricks.com
-- Date:    2026-09-26
--
-- Purpose:
--   Define a fail-closed row-filter function bound to the synthetic care_unit
--   dimension (MICU / SICU / CCU) and apply it to the two operational gold tables
--   (census and patient_features).
--
--   Fail-closed semantics: a user who belongs to NONE of the four groups
--   (icu_admins, icu_micu, icu_sicu, icu_ccu) matches no branch of the RETURN
--   expression → the function returns FALSE for every row → the user sees 0 rows.
--   There is no default-allow fallback.
--
-- WARNING — MATERIALIZED VIEW metadata loss:
--   Like governance.sql, this file MUST be re-run after any pipeline recreate.
--   Databricks drops and recreates the Materialized View objects during a full
--   pipeline refresh, which silently removes all SET ROW FILTER bindings.
--   Re-running is safe: CREATE OR REPLACE on the function is idempotent, and
--   ALTER TABLE ... SET ROW FILTER overwrites the existing binding.
--
-- Live deploy steps (performed by the controller, NOT in this file):
--   1. Create UC account groups: icu_admins, icu_micu, icu_sicu, icu_ccu.
--   2. Run this SQL file against the sandbox warehouse.
--   3. Add the app service principal to icu_admins.
--   4. Verify: as icu_admins → 40 rows; as icu_micu → MICU rows only;
--      as a member of no group → 0 rows.
--
-- ⚠ GOVERNANCE SCOPE — UC filter vs. Lakebase app path:
--   This row filter governs DIRECT Unity Catalog / SQL-warehouse access to
--   gold.census and gold.patient_features. It does NOT apply to the Databricks
--   App, which reads Lakebase-synced Postgres copies (mimic_iii.census,
--   mimic_iii.patient_features) using the app service principal (icu_admins).
--   Because the app SP is in icu_admins, it sees all rows from all care units;
--   the UC row filter is bypassed on the Lakebase path entirely.
--
--   App-level per-team scoping is a documented follow-up (not implemented here).
--   See README.md § Governance and
--   app/src/icu_step_down/backend/lib/access.py (care_unit_filter_for_user).
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Row-filter function: fail-closed unit scoping
--
-- Returns TRUE when the authenticated user is either:
--   (a) a member of icu_admins  → sees all rows regardless of care_unit, or
--   (b) a member of the group matching the row's care_unit value.
--
-- A user in none of the four groups matches no branch → returns FALSE → sees
-- no rows (default deny).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION icu_step_down.gold.rls_care_unit(care_unit STRING)
RETURN
     is_account_group_member('icu_admins')
  OR (care_unit = 'MICU' AND is_account_group_member('icu_micu'))
  OR (care_unit = 'SICU' AND is_account_group_member('icu_sicu'))
  OR (care_unit = 'CCU'  AND is_account_group_member('icu_ccu'));
-- Default deny: a user in none of these groups matches no branch → sees no rows.

-- ---------------------------------------------------------------------------
-- Bind the row filter to the two operational gold tables.
-- The filter argument ON (care_unit) maps each row's care_unit column value
-- to the care_unit parameter of rls_care_unit above.
-- ---------------------------------------------------------------------------
ALTER TABLE icu_step_down.gold.census           SET ROW FILTER icu_step_down.gold.rls_care_unit ON (care_unit);
ALTER TABLE icu_step_down.gold.patient_features SET ROW FILTER icu_step_down.gold.rls_care_unit ON (care_unit);
