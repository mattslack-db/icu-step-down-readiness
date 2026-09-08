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

Note: bronze.chart_events had 37,625,847 scoped rows; silver.vital_signs has 21,771,413
after filtering NULL VALUENUM, ERROR IS NULL, icustay_id IS NOT NULL, and plausibility
ranges. Reduction of ~42% is expected (many chart_events lack icustay_id linkage).

## Transformation Notes

- Column names downcased from UPPERCASE MIMIC-III convention
- Temperature items 678/223761 (Fahrenheit) converted to Celsius: (F-32)*5/9
- MetaVision GCS recorded as three components: Eye (220739), Verbal (223900),
  Motor (223901); CareVue records GCS total directly (198). All stored as vital_name='gcs'.
- Lactate convenience flag added to silver.lab_events: `is_lactate = (ITEMID = 50813)`
  (verified: 187,116 lactate observations in bronze)

_(Aggregates only — no raw patient rows.)_
