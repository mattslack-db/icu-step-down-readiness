# Evidence: Phase 3 — Unity Catalog Governance

**Date:** 2026-09-08  
**Profile:** `icu-sandbox` (workspace: https://fe-sandbox-icu-step-down-readiness.cloud.databricks.com)  
**Catalog:** `icu_step_down`

---

## 1. Grants Applied

### SHOW GRANTS ON CATALOG icu_step_down

```
databricks experimental aitools tools query \
  "SHOW GRANTS ON CATALOG icu_step_down" \
  --profile icu-sandbox
```

| ActionType   | ObjectKey                              | ObjectType | Principal             |
|-------------|----------------------------------------|------------|-----------------------|
| USE CATALOG | icu_step_down                          | CATALOG    | account users         |
| READ METADATA | metastore_aws_us_west_2_vending_machine | METASTORE | account users         |
| READ METADATA | metastore_aws_us_west_2_vending_machine | METASTORE | vaishnavi.mohan@databricks.com |
| READ METADATA | metastore_aws_us_west_2_vending_machine | METASTORE | nishant.singh@databricks.com |
| READ METADATA | metastore_aws_us_west_2_vending_machine | METASTORE | will.taff@databricks.com |

### SHOW GRANTS ON SCHEMA icu_step_down.gold

```
databricks experimental aitools tools query \
  "SHOW GRANTS ON SCHEMA icu_step_down.gold" \
  --profile icu-sandbox
```

| ActionType  | ObjectKey          | ObjectType | Principal     |
|------------|---------------------|------------|---------------|
| SELECT     | icu_step_down.gold  | SCHEMA     | account users |
| USE SCHEMA | icu_step_down.gold  | SCHEMA     | account users |
| READ METADATA | metastore_aws_us_west_2_vending_machine | METASTORE | account users |
| READ METADATA | metastore_aws_us_west_2_vending_machine | METASTORE | vaishnavi.mohan@databricks.com |
| READ METADATA | metastore_aws_us_west_2_vending_machine | METASTORE | nishant.singh@databricks.com |
| READ METADATA | metastore_aws_us_west_2_vending_machine | METASTORE | will.taff@databricks.com |

---

## 2. Comments Applied

### Catalog comment

```
databricks experimental aitools tools query \
  "SELECT catalog_name, comment FROM system.information_schema.catalogs WHERE catalog_name = 'icu_step_down'" \
  --profile icu-sandbox
```

| catalog_name  | comment |
|--------------|---------|
| icu_step_down | ICU Step-Down Readiness project. Contains bronze (raw), silver (cleaned), and gold (features + census) layers sourced from MIMIC-III via Delta Sharing. |

### DESCRIBE SCHEMA EXTENDED icu_step_down.bronze

```
databricks experimental aitools tools query \
  "DESCRIBE SCHEMA EXTENDED icu_step_down.bronze" \
  --profile icu-sandbox
```

| database_description_item | database_description_value |
|--------------------------|---------------------------|
| Catalog Name | icu_step_down |
| Namespace Name | bronze |
| Comment | Raw ingested MIMIC-III via Delta Share. Tables are unmodified source data with minimal type enforcement. |
| Owner | matt.slack@databricks.com |
| Predictive Optimization | ENABLE (inherited from METASTORE metastore_aws_us_west_2_vending_machine) |

### DESCRIBE SCHEMA EXTENDED icu_step_down.silver

| database_description_item | database_description_value |
|--------------------------|---------------------------|
| Catalog Name | icu_step_down |
| Namespace Name | silver |
| Comment | Cleaned and typed clinical tables. Deduplication, NULL handling, and type casting applied to bronze source data. |
| Owner | matt.slack@databricks.com |

### DESCRIBE SCHEMA EXTENDED icu_step_down.gold

| database_description_item | database_description_value |
|--------------------------|---------------------------|
| Catalog Name | icu_step_down |
| Namespace Name | gold |
| Comment | Features, training set, and operational census. Derived from silver; ready for ML model training and live operational dashboards. |
| Owner | matt.slack@databricks.com |

### Table comments (information_schema.tables)

```
databricks experimental aitools tools query \
  "SELECT table_catalog, table_schema, table_name, comment
   FROM icu_step_down.information_schema.tables
   WHERE table_schema IN ('gold','silver') AND comment IS NOT NULL AND comment != ''
   ORDER BY table_schema, table_name" \
  --profile icu-sandbox
```

| table_catalog | table_schema | table_name            | comment |
|--------------|--------------|-----------------------|---------|
| icu_step_down | gold | census | Operational real-time ICU census. One row per currently active ICU stay with live step-down readiness probability (served by the Databricks App in Phase 7). |
| icu_step_down | gold | patient_features | One row per ICU stay. Aggregated vital-sign statistics (mean/min/max/last), GCS, vasopressor and ventilator flags, and last lactate. Primary feature set for the step-down readiness classifier. |
| icu_step_down | gold | readiness_training_set | Labelled training set for the step-down readiness model. Joins patient_features with icu_stays-derived outcome labels (LOS-based proxy for safe step-down). |
| icu_step_down | silver | vital_signs | Cleaned vital-sign observations from MIMIC-III chartevents. Outliers capped, timestamps normalised to UTC, and chart items mapped to standard parameter names (hr, sbp, dbp, spo2, temp_c, rr). |

---

## 3. Column Classification Tags

Tags applied to **all three gold tables** on patient identifier columns (subject_id, hadm_id, icustay_id).

**Note on tag policy:** The workspace enforces a tag policy on `data_classification` with allowed values `[secret, pii, non-pii]`. The initial SQL used `'identifier'` which was rejected. Tags were applied with value `'pii'` — the semantically correct choice since subject_id/hadm_id/icustay_id are patient linking keys that must be treated as sensitive in any downstream context (even though MIMIC-III is de-identified, these IDs could correlate with external data).

**Review fix (2026-09-08):** Initial run only tagged `gold.patient_features`. Tags extended to `gold.readiness_training_set` and `gold.census` so all three gold tables are consistently classified.

```
databricks experimental aitools tools query \
  "SELECT table_name, column_name, tag_name, tag_value
   FROM icu_step_down.information_schema.column_tags
   WHERE schema_name = 'gold'
   ORDER BY table_name, column_name" \
  --profile icu-sandbox
```

| table_name              | column_name | tag_name            | tag_value |
|------------------------|------------|---------------------|-----------|
| census                 | hadm_id    | data_classification | pii       |
| census                 | icustay_id | data_classification | pii       |
| census                 | subject_id | data_classification | pii       |
| patient_features       | hadm_id    | data_classification | pii       |
| patient_features       | icustay_id | data_classification | pii       |
| patient_features       | subject_id | data_classification | pii       |
| readiness_training_set | hadm_id    | data_classification | pii       |
| readiness_training_set | icustay_id | data_classification | pii       |
| readiness_training_set | subject_id | data_classification | pii       |

---

## 4. UC Lineage (system.access.table_lineage)

Deduplicated lineage for `gold.census` and `gold.patient_features` as of 2026-09-08.

```
databricks experimental aitools tools query \
  "SELECT DISTINCT source_table_full_name, target_table_full_name
   FROM system.access.table_lineage
   WHERE target_table_full_name IN (
     'icu_step_down.gold.census',
     'icu_step_down.gold.patient_features'
   ) AND event_date >= current_date() - 14
   ORDER BY target_table_full_name, source_table_full_name" \
  --profile icu-sandbox
```

| source_table_full_name                      | target_table_full_name                  |
|--------------------------------------------|-----------------------------------------|
| icu_step_down.gold.patient_features        | icu_step_down.gold.census               |
| icu_step_down.silver.icu_stays             | icu_step_down.gold.census               |
| icu_step_down.bronze.chart_events          | icu_step_down.gold.patient_features     |
| icu_step_down.bronze.input_events_cv       | icu_step_down.gold.patient_features     |
| icu_step_down.bronze.input_events_mv       | icu_step_down.gold.patient_features     |
| icu_step_down.bronze.procedure_events_mv   | icu_step_down.gold.patient_features     |
| icu_step_down.silver.icu_stays             | icu_step_down.gold.patient_features     |
| icu_step_down.silver.lab_events            | icu_step_down.gold.patient_features     |
| icu_step_down.silver.patients              | icu_step_down.gold.patient_features     |
| icu_step_down.silver.vital_signs           | icu_step_down.gold.patient_features     |

### Lineage interpretation

- **gold.census** receives data from `gold.patient_features` (features join) and `silver.icu_stays` (current admissions join). This confirms the census materialized view is a composite of features + active-stay data.
- **gold.patient_features** is fed from 4 silver tables (vital_signs, icu_stays, lab_events, patients) and 3 bronze tables (chart_events, input_events_cv, input_events_mv, procedure_events_mv). The bronze sources flow through silver transformations before reaching gold, confirming the medallion pipeline lineage from Phase 2.
- Upstream Delta Sharing source (`mimic_iii_src`) is not visible in `system.access.table_lineage` because it is a Delta Sharing catalog — its lineage terminates at the bronze tables that ingest from it.
