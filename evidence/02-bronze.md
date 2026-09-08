# Evidence: Bronze Layer (Phase 2, Task 2.1)

**Pipeline:** icu-step-down-readiness-medallion  
**Pipeline ID:** 7b407204-d430-492e-b20b-239a1188803f  
**Update ID:** 91a0a023-38a5-4791-8e09-05f55d640f7e  
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
| chart_events (scoped) | 38,776,289 |
| lab_events | 27,854,055 |
| d_labitems | 753 |
| prescriptions | 4,156,450 |
| input_events_cv | 17,527,935 |
| input_events_mv | 3,618,991 |
| procedure_events_mv | 258,066 |
| services | 73,343 |

## chart_events Scope

chart_events is filtered to vital-sign, GCS, and ventilator-mode itemids (original table ~330M rows).
Filtered to 38,776,289 rows — approximately 12% of the full table.
Added ventilator-mode itemids (720, 722, 223849) in v2 to support CareVue on_ventilator detection.

| Category | Itemids | Rows |
|----------|---------|------|
| heart_rate | 211, 220045 | 7,943,034 |
| resp_rate | 615, 618, 220210, 224690 | 6,940,625 |
| systolic_bp | 51, 442, 455, 6701, 220179, 220050 | 6,138,363 |
| diastolic_bp | 8368, 8440, 8441, 8555, 220180, 220051 | 6,119,902 |
| spo2 | 646, 220277 | 6,090,733 |
| gcs | 198, 220739, 223900, 223901 | 2,644,463 |
| temperature | 676, 678, 223761, 223762 | 1,748,727 |
| ventilator_mode | 720 (CV Vent Mode), 722 (CV Vent Type), 223849 (MV Vent Mode) | 1,150,442 |

## Schema Notes

- MIMIC-III columns are UPPERCASE (e.g. SUBJECT_ID, ITEMID, VALUENUM)
- Delta Sharing catalog is read-only; materialized views used (no streaming/CDF)
- d_items was NOT shared; vasopressor/ventilator itemids sourced from MIMIC-III documentation

_(Aggregates only — no raw patient rows.)_
