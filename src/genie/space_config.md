# Genie Space Configuration — ICU Step-Down Readiness

## Space Metadata

| Field | Value |
|-------|-------|
| **Title** | ICU Step-Down Readiness |
| **Space ID** | `01f1ab768fd619ca954173c4f147dc93` |
| **Warehouse** | Serverless Starter Warehouse (`7cdc2b0c4ec592d8`) |
| **Workspace URL** | `https://fe-sandbox-icu-step-down-readiness.cloud.databricks.com/genie/rooms/01f1ab768fd619ca954173c4f147dc93` |
| **Parent path** | `/Workspace/Users/matt.slack@databricks.com/genie_spaces` |
| **Created** | 2026-09-08 (Phase 6 of ICU Step-Down Readiness build) |

**Space description:** Natural language exploration of ICU patient step-down readiness data. Covers current census (40 patients), 61K historical stays with readiness outcomes, and time-series vitals. Answers questions about who is ready for step-down, bounce-back rates, length of stay, vasopressor/ventilator use, and vital signs by patient cohort.

---

## Tables Exposed

Three Unity Catalog tables are attached. `icu_step_down.gold.patient_features` was intentionally excluded: `readiness_training_set` is a strict superset (all same columns plus `readiness_label`) and including both would confuse Genie's table selection.

### 1. `icu_step_down.gold.census`

**Purpose:** Current ICU patient census — 40 active patients with latest features.  
**Use when:** Questions mention "current", "today", or "active" ICU patients.  
**Row count:** 40  
**Key fields:**

| Column | Type | Description |
|--------|------|-------------|
| `icustay_id` | string | ICU stay ID. Joins to `readiness_training_set` for outcome data. |
| `age` | decimal | Patient age in years at admission. |
| `los` | string | ICU length of stay in **days** (cast to DOUBLE for math). |
| `on_vasopressors` | boolean | True if currently on vasopressor drugs (norepinephrine etc.). Step-down contra-indicator. |
| `on_ventilator` | boolean | True if currently on mechanical ventilation. Step-down contra-indicator. |
| `gcs_last` | string | Glasgow Coma Scale **total** score, range 3–15. 15 = fully alert. Cast to DOUBLE. |
| `hr_mean` | double | Mean heart rate (bpm) over 24h window. **NULL for 37/40 patients.** |
| `lactate_last` | string | Last lactate mmol/L. NULL if not measured. |

**Data quality note:** 37 of 40 census patients have NULL vital aggregates (hr_mean, sbp_mean, etc.). Use `on_vasopressors`/`on_ventilator` booleans for direct census queries; JOIN to `readiness_training_set` on `icustay_id` for vitals or readiness labels.

---

### 2. `icu_step_down.gold.readiness_training_set`

**Purpose:** Historical ICU stays with 24-hour vital aggregates and step-down readiness outcomes.  
**Row count:** 61,532  
**Key fields:**

| Column | Type | Description |
|--------|------|-------------|
| `icustay_id` | string | ICU stay ID. Joins to `census` and `silver.vital_signs`. |
| `readiness_label` | int | **1** = safe step-down (no bounce-back). **0** = returned to ICU within 72h (bounce-back). 97% are label=1 (59,706 ready; 1,826 bounce-back). |
| `age` | decimal | Patient age in years. |
| `los` | string | ICU length of stay in **days** (cast to DOUBLE). NULL for 10 rows. |
| `hr_mean` | double | Mean heart rate (bpm). NULL for ~41% of stays. |
| `gcs_last` | string | Glasgow Coma Scale total (3–15). NULL for ~53% of stays. |
| `on_vasopressors` | boolean | Required vasopressor support. |
| `on_ventilator` | boolean | Required mechanical ventilation. |
| `lactate_last` | string | Last lactate mmol/L. NULL for ~39% of stays. |
| `sbp_mean` | double | Mean systolic BP mmHg. NULL for ~53% of stays. |

**Data quality note:** Always filter `IS NOT NULL` when averaging hr_mean or gcs_last.  
**Excluded columns** (hidden from Genie): `subject_id`, `hadm_id`.

---

### 3. `icu_step_down.silver.vital_signs`

**Purpose:** Time-series vital measurements — one row per reading.  
**Row count:** 21,771,413  
**Key fields:**

| Column | Type | Description |
|--------|------|-------------|
| `icustay_id` | string | ICU stay ID. Join to census or readiness_training_set. |
| `charttime` | timestamp | When the reading was recorded. |
| `vital_name` | string | Vital type: `hr`, `sbp`, `dbp`, `spo2`, `temp_c`, `rr`, `gcs`. |
| `value` | string | Measured value (cast to DOUBLE for arithmetic). |

**Data quality note:** Always include a WHERE clause on `icustay_id` or `charttime` — full table scans on 21.7M rows are slow.  
**Excluded columns** (hidden from Genie): `subject_id`.

---

## Example SQL Queries (Configured in Space)

All SQL is qualified with table aliases to prevent the "Table name or alias is required for column" error.

### Q1 — Current patients ready for step-down
```sql
SELECT
  SUM(CASE WHEN r.readiness_label = 1 THEN 1 ELSE 0 END) AS ready_for_step_down,
  SUM(CASE WHEN r.readiness_label = 0 THEN 1 ELSE 0 END) AS not_ready,
  COUNT(*) AS total_current_patients
FROM icu_step_down.gold.census c
INNER JOIN icu_step_down.gold.readiness_training_set r
  ON c.icustay_id = r.icustay_id
```

### Q2 — Average LOS by readiness band
```sql
SELECT
  r.readiness_label,
  CASE WHEN r.readiness_label = 1 THEN 'Ready (safe step-down)'
       ELSE 'Not ready (bounce-back risk)' END AS readiness_band,
  ROUND(AVG(CAST(r.los AS DOUBLE)), 2) AS avg_los_days,
  COUNT(*) AS num_stays
FROM icu_step_down.gold.readiness_training_set r
WHERE r.los IS NOT NULL
GROUP BY r.readiness_label
ORDER BY r.readiness_label
```

### Q3 — Current patients on vasopressors and ventilator
```sql
SELECT
  SUM(CASE WHEN c.on_vasopressors AND c.on_ventilator THEN 1 ELSE 0 END) AS on_both,
  SUM(CASE WHEN c.on_vasopressors THEN 1 ELSE 0 END) AS on_vasopressors_only,
  SUM(CASE WHEN c.on_ventilator THEN 1 ELSE 0 END) AS on_ventilator_only,
  COUNT(*) AS total_patients
FROM icu_step_down.gold.census c
```

### Q4 — Avg HR and GCS for patients over 65
```sql
SELECT
  ROUND(AVG(r.hr_mean), 1) AS avg_heart_rate_bpm,
  ROUND(AVG(CAST(r.gcs_last AS DOUBLE)), 1) AS avg_gcs_score,
  COUNT(*) AS num_stays
FROM icu_step_down.gold.readiness_training_set r
WHERE r.age > 65
  AND r.hr_mean IS NOT NULL
  AND r.gcs_last IS NOT NULL
```

### Q5 — Bounce-back fraction
```sql
SELECT
  ROUND(SUM(CASE WHEN r.readiness_label = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS bounce_back_pct,
  SUM(CASE WHEN r.readiness_label = 0 THEN 1 ELSE 0 END) AS bounce_back_count,
  COUNT(*) AS total_stays
FROM icu_step_down.gold.readiness_training_set r
```

---

## Text Instructions

The space includes one text instructions block with the following sections:

### PURPOSE
- Answer clinical and analytical questions about ICU step-down readiness, patient vitals, length of stay, and bounce-back outcomes.
- Users are ICU clinicians and data analysts.

### DISAMBIGUATION
- "Current patients" or "census" = the 40 active ICU patients in the census table.
- "Ready for step-down" or "readiness band 1" = readiness_label = 1 in readiness_training_set.
- "Bounce-back" = patient returned to ICU within 72 hours; these have readiness_label = 0.
- "Readiness band" means GROUP BY readiness_label (1 = ready, 0 = not ready).
- GCS (gcs_last) is the Glasgow Coma Scale TOTAL score, range 3–15; higher is better; 15 = fully alert.
- `los` is in DAYS stored as string; use CAST(los AS DOUBLE) for arithmetic.
- Readiness label is an outcome (0 or 1), not a probability score.

### DATA QUALITY NOTES
- census: 37 of 40 patients have NULL vital aggregates; use on_vasopressors and on_ventilator booleans for census filters; join to readiness_training_set on icustay_id to get vitals or readiness for current patients.
- readiness_training_set: hr_mean NULL in 41% of stays, gcs_last NULL in 53%; filter IS NOT NULL when computing averages.
- silver.vital_signs is 21.7M rows; always filter by icustay_id or charttime.

### CONSTRAINTS
- Return aggregates only (COUNT, AVG, SUM, ROUND); do not return individual patient rows.
- Do not use SELECT *.

---

## Reproducibility

The full `serialized_space` JSON is in `src/genie/genie_agent.json`. To recreate:

```bash
cd src/genie
databricks workspace mkdirs /Workspace/Users/<email>/genie_spaces --profile icu-sandbox
databricks genie create-space --profile icu-sandbox --json "{
  \"warehouse_id\": \"7cdc2b0c4ec592d8\",
  \"title\": \"ICU Step-Down Readiness\",
  \"description\": \"...\",
  \"parent_path\": \"/Workspace/Users/<email>/genie_spaces\",
  \"serialized_space\": \$(cat genie_agent.json | jq -c '.' | jq -Rs '.')
}"
```
