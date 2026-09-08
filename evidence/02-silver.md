# Evidence: Silver Layer (Phase 2, Task 2.2)

**Pipeline:** icu-step-down-readiness-medallion  
**Status:** COMPLETED  
**Source:** `icu_step_down.bronze.*`  
**Target:** `icu_step_down.silver.*` (materialized views, cleaned + typed)

## Row Counts

| Table | Rows |
|-------|------|
| silver.patients | 46,520 |
| silver.icu_stays | 61,532 |
| silver.vital_signs | 21,771,413 |
| silver.lab_events | 24,932,835 |

## silver.patients — Gender Distribution

| gender | count |
|--------|-------|
| F | 20,399 |
| M | 26,121 |

## silver.icu_stays — LOS Statistics

| metric | value |
|--------|-------|
| min_los (days) | 0.0001 |
| avg_los (days) | 4.92 |
| max_los (days) | 99.46 |
| total rows | 61,532 |

## silver.vital_signs — Distribution by Vital Name

Rows after physiological plausibility filtering:

| vital_name | rows |
|------------|------|
| hr | 5,171,415 |
| rr | 3,775,741 |
| sbp | 3,664,940 |
| dbp | 3,663,678 |
| spo2 | 3,409,222 |
| temp_c | 1,141,834 |
| gcs | 944,583 |
| **total** | **21,771,413** |

## GCS Value Distribution (vital_name='gcs')

GCS values verified as unified 3–15 total for both eras:
- CareVue itemid 198: GCS total directly (unchanged)
- MetaVision: Eye (220739) + Verbal (223900) + Motor (223901) SUMmed per
  (icustay_id, charttime); only charttimes with all 3 components are emitted

| gcs_total | count |
|-----------|-------|
| 3 | 60,183 |
| 4 | 8,926 |
| 5 | 7,354 |
| 6 | 36,152 |
| 7 | 43,149 |
| 8 | 48,012 |
| 9 | 57,611 |
| 10 | 102,033 |
| 11 | 114,506 |
| 12 | 9,979 |
| 13 | 24,303 |
| 14 | 75,251 |
| 15 | 357,124 |

GCS range confirmed 3–15. Average GCS total ≈ 11.4 (moderately impaired to normal, expected for a mixed ICU population).

## Transformation Notes

- Column names downcased from UPPERCASE MIMIC-III convention
- Temperature items 678/223761 (Fahrenheit) converted to Celsius: (F-32)*5/9
- GCS is a unified 3–15 total: CareVue via itemid 198 directly; MetaVision via
  SUM(Eye 220739, Verbal 223900, Motor 223901) per (icustay_id, charttime), 
  requiring all 3 components to be present before emitting a row
- Ventilator-mode itemids (720, 722, 223849) are ingested in bronze.chart_events
  but consumed by gold.patient_features directly (not emitted as vital_signs rows)
- Lactate convenience flag in silver.lab_events: `is_lactate = (ITEMID = 50813)`
  (verified: 187,116 lactate observations in bronze)

_(Aggregates only — no raw patient rows.)_
