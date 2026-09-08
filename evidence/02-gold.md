# Evidence: Gold Layer (Phase 2, Task 2.3)

**Pipeline:** icu-step-down-readiness-medallion  
**Status:** COMPLETED  
**Source:** `icu_step_down.silver.*`  
**Target:** `icu_step_down.gold.*` (materialized views)

## Row Counts

| Table | Rows |
|-------|------|
| gold.patient_features | 61,532 |
| gold.readiness_training_set | 61,532 |
| gold.census | 40 |

## gold.patient_features — Vasopressor / Ventilator Prevalence

| on_vasopressors | on_ventilator | count |
|-----------------|---------------|-------|
| false | false | 32,342 |
| false | true | 11,966 |
| true | true | 14,017 |
| true | false | 3,207 |

Vasopressor rate: 27.9% of ICU stays (17,224 / 61,532)  
Ventilator rate: 42.2% of ICU stays (25,983 / 61,532)

Note: ventilator rate increased from 15.9% (v1, MetaVision only) to 42.2% (v2)
after adding CareVue itemids 720/722 and MetaVision 223849 to on_ventilator detection.
The CareVue cohort (~40% of MIMIC stays) was not captured by procedure_events_mv alone.

## gold.readiness_training_set — Label Balance

| readiness_label | count | pct |
|-----------------|-------|-----|
| 0 (not ready / bounce-back) | 1,826 | 3.0% |
| 1 (successful step-down) | 59,706 | 97.0% |

**Label proxy:** label=1 when ICU stay has OUTTIME IS NOT NULL AND no subsequent ICU
stay begins within 72h (no bounce-back). Label=0 for still-in-ICU or bounce-back.

Note: 97/3 imbalance is expected for MIMIC-III (retrospective; most stays ended
successfully). ML training phase will need class-weighting or SMOTE.

## gold.census — Design Decision

MIMIC-III is fully retrospective; `outtime IS NULL` returns ~0 rows. Therefore the
census is defined as the 40 most recent ICU stays by intime, providing a non-empty
representative snapshot for the app's operational scoring view.

## Sample Rows — gold.patient_features (5 rows, aggregates only)

| icustay_id | age | los | hr_mean | sbp_mean | spo2_mean | rr_mean | on_vaso | on_vent | gcs_last | lactate_last |
|-----------|-----|-----|---------|----------|-----------|---------|---------|---------|----------|--------------|
| 204546 | 59.5 | 1.97 | 72.0 | 153.9 | 98.2 | 15.0 | false | false | 15 | 1.1 |
| 207789 | 25.9 | 6.08 | 101.0 | 145.1 | 95.3 | 27.1 | false | false | 15 | 3.4 |
| 212885 | 57.4 | 1.75 | 96.5 | 108.7 | 96.8 | 29.5 | false | false | 15 | 1.5 |
| 216700 | 38.2 | 0.98 | 80.1 | 118.9 | 98.0 | 17.8 | false | false | 15 | 1.5 |
| 220253 | 66.6 | 0.81 | 73.1 | 104.5 | 98.3 | 16.5 | false | false | 15 | null |

_(Note: some stays have NULL vital aggregates — those are short stays with no matching
scoped chart_events, typically <1h duration where vitals weren't charted to the system.)_

_(Aggregates and ICU stay IDs only — no raw patient rows or free-text data.)_
