# Evidence: Data Access (Phase 1, Task 1.1) — RISK GATE CLEARED

**Result:** Delta Sharing path works. Real MIMIC-III is readable from the sandbox. No fallback needed.

## Source
- Workspace: `e2-demo-field-eng.cloud.databricks.com` (CLI profile `DEFAULT`)
- Catalog/schema: `hls_healthcare.mimic_iii`
- Metastore: `aws:us-west-2:b169b504-4c54-49f2-bc3a-adf4b128f36d` (`databricks-field-eng-e2demo`)

## Sandbox (recipient)
- Workspace: `fe-sandbox-icu-step-down-readiness.cloud.databricks.com` (CLI profile `icu-sandbox`)
- Metastore: `aws:us-west-2:646f2b9a-d861-4deb-92f2-9927875bcc60` (shared FEVM vending-machine metastore)

## Delta Sharing setup (cross-metastore D2D, same region us-west-2)
- **Provider side** (`DEFAULT`): created share `icu_step_down_mimic_iii`; added 23 canonical MIMIC-III tables; granted `SELECT` to recipient `recipient_learn_to_be` (the pre-existing recipient for the sandbox's shared metastore — a second recipient with the same sharing id is disallowed).
- **Recipient side** (`icu-sandbox`): provider appears as `databricks-field-eng` (owner: account users); created shared catalog `mimic_iii_src` (type `DELTASHARING_CATALOG`) from share `icu_step_down_mimic_iii`.

## Consumption path for the pipeline (Phase 2)
- Read raw tables from **`mimic_iii_src.mimic_iii.<table>`** on the `icu-sandbox` profile.

## Verification (queries run on the sandbox through the share)

```
SELECT COUNT(*) AS patients FROM mimic_iii_src.mimic_iii.patients;
-- [ { "patients": "46520" } ]

SELECT COUNT(*) AS icu_stays FROM mimic_iii_src.mimic_iii.icu_stays;
-- [ { "icu_stays": "61532" } ]
```

23 tables shared: admissions, callout, caregivers, chart_events, cpt_events, d_icd_diagnoses, d_icd_procedures, d_labitems, diagnoses_icd, drg_codes, icu_stays, input_events_cv, input_events_mv, lab_events, microbiology_events, note_events, output_events, patients, prescriptions, procedure_events_mv, procedures_icd, services, transfers.

_(Counts/aggregates only — no raw patient rows committed.)_
