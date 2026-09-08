# Evidence: Bronze Layer (Phase 2, Task 2.1)

**Pipeline:** icu-step-down-readiness-medallion  
**Pipeline ID:** 453a02bb-8c74-4bed-a608-c7041c36da28  
**Update ID:** a3a1ce3e-ce3d-4466-8f57-72e1d328ee2e  
**Status:** COMPLETED  
**Source:** `mimic_iii_src.mimic_iii.*` (Delta Sharing, read-only)  
**Target:** `icu_step_down.bronze.*` (materialized views)

## Row Counts

| Table | Rows |
|-------|------|
| patients | 46,520 |
| admissions | 58,976 |
| icu_stays | 61,532 |
| transfers | 261,897 |
| chart_events (scoped) | 37,625,847 |
| lab_events | 27,854,055 |
| d_labitems | 753 |
| prescriptions | 4,156,450 |
| input_events_cv | 17,527,935 |
| input_events_mv | 3,618,991 |
| procedure_events_mv | 258,066 |
| services | 73,343 |

## chart_events Scope Decision

chart_events is filtered to vital-sign + GCS itemids only (original table ~330M rows).  
Filtered to 37,625,847 rows — approximately 11% of the full table.

| Category | Itemids | Rows |
|----------|---------|------|
| heart_rate | 211, 220045 | 7,943,034 |
| resp_rate | 615, 618, 220210, 224690 | 6,940,625 |
| systolic_bp | 51, 442, 455, 6701, 220179, 220050 | 6,138,363 |
| diastolic_bp | 8368, 8440, 8441, 8555, 220180, 220051 | 6,119,902 |
| spo2 | 646, 220277 | 6,090,733 |
| gcs | 198, 220739, 223900, 223901 | 2,644,463 |
| temperature | 676, 678, 223761, 223762 | 1,748,727 |

## Schema Notes

- MIMIC-III columns are UPPERCASE (e.g. SUBJECT_ID, ITEMID, VALUENUM)
- Delta Sharing catalog is read-only; materialized views used (no streaming/CDF)
- d_items was NOT shared (23 tables exclude it); vasopressor/ventilator itemids
  resolved from MIMIC-III literature documentation instead

_(Aggregates only — no raw patient rows.)_
