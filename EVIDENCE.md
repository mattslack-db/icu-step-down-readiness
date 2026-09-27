# Execution Evidence — this build actually ran end to end

This file embeds **verbatim, committed run output** from live executions against the
Databricks sandbox `fe-sandbox-icu-step-down-readiness` (CLI profile `icu-sandbox`).
It is readable text, not screenshots and not narrative description. The full raw
captures live in [`evidence/raw/`](evidence/raw/); the key results are reproduced
inline here so the evidence is visible without descending into the tree.

Layers proven: **Lakeflow pipeline → Unity Catalog gold → Mosaic AI serving →
Genie → Lakebase → Databricks App**, plus the drift-monitoring and unit-access
enhancements.

---

## 1. Lakeflow pipeline run — bronze → silver → gold (COMPLETED)

`databricks pipelines start-update` on `icu-step-down-readiness-medallion`
(pipeline `f216d643-…`, update `a28ac017-…`, 2026-09-25). Update state `COMPLETED`;
per-layer row counts queried immediately after the run:

```
layer    table                    rows
bronze   admissions               58,976
bronze   chart_events             38,776,289
bronze   icu_stays                61,532
bronze   lab_events               27,854,055
bronze   patients                 46,520
bronze   transfers                261,897
silver   icu_stays                61,532
silver   lab_events               24,932,835
silver   patients                 46,520
silver   vital_signs              21,771,413
gold     patient_features         61,532
gold     readiness_training_set   61,532
gold     census                   40      (current ICU patients)
```

Full event log (every flow `COMPLETED`, bronze→silver→gold): [`evidence/raw/pipeline-run.txt`](evidence/raw/pipeline-run.txt).

---

## 2. Query results against the governed gold tables (Unity Catalog)

`databricks experimental aitools tools query` on `icu_step_down.gold.*`
(serverless SQL warehouse):

```
-- readiness_training_set label balance (bounce-back proxy)
readiness_label   n        pct
0 (not ready)     1,826    3.0%
1 (ready)         59,706   97.0%

-- vasopressor / ventilator prevalence (patient_features, n=61,532)
on_vasopressors  on_ventilator   n
false            false           32,342
false            true            11,966
true             false           3,207
true             true            14,017

-- current census cohort summary (n=40)
avg_age  avg_los_days  on_pressors  on_vent  patients
54.8     2.83          8            11       40
```

Full queries + sample feature rows: [`evidence/raw/gold-queries.txt`](evidence/raw/gold-queries.txt).

---

## 3. Real served prediction — Mosaic AI endpoint `icu-readiness`

`databricks serving-endpoints query icu-readiness` (model
`icu_step_down.ml.readiness_model` v2), two patients, 30 features each. Verbatim response:

```json
{
  "predictions": [
    { "prediction": "{\"readiness_score\": 0.4738641185, \"factors\": [
        {\"name\": \"lactate_last\", \"direction\": \"risk\", \"magnitude\": 0.2617},
        {\"name\": \"on_ventilator\", \"direction\": \"risk\", \"magnitude\": 0.0299},
        {\"name\": \"rr_last\", \"direction\": \"supports\", \"magnitude\": 0.0286}]}" },
    { "prediction": "{\"readiness_score\": 0.4631745729, \"factors\": [
        {\"name\": \"lactate_last\", \"direction\": \"risk\", \"magnitude\": 0.1997},
        {\"name\": \"rr_min\", \"direction\": \"risk\", \"magnitude\": 0.1099},
        {\"name\": \"hr_mean\", \"direction\": \"supports\", \"magnitude\": 0.0797}]}" }
  ]
}
```

Note `on_ventilator` is returned as **`"risk"`** — the always-flag-known-risks
safety override, live. Full request + response: [`evidence/raw/serving-prediction.txt`](evidence/raw/serving-prediction.txt).

---

## 4. Genie natural-language Q&A over the governed tables

Genie Conversation API, space `01f1b92aeef914e383e43c1452d294cf`. Each question →
generated SQL → result rows (verbatim):

**Q1 — "How many current ICU patients are ready for step-down?"**
```sql
SELECT SUM(CASE WHEN r.readiness_label = 1 THEN 1 ELSE 0 END) AS ready_for_step_down,
       SUM(CASE WHEN r.readiness_label = 0 THEN 1 ELSE 0 END) AS not_ready,
       COUNT(*) AS total_current_patients
FROM icu_step_down.gold.census c
JOIN icu_step_down.gold.readiness_training_set r ON c.icustay_id = r.icustay_id
```
→ `ready_for_step_down=38, not_ready=2, total_current_patients=40`

**Q3 — "How many current patients are on vasopressors and a ventilator at the same time?"**
→ `on_both=5, on_vasopressors=8, on_ventilator=11, total_patients=40`

**Q5 — "What fraction of ICU stays had a bounce-back within 72 hours?"**
→ `bounce_back_pct=2.97, bounce_back_count=1826, total_stays=61532`

All five Q&A with full SQL + rows: [`evidence/raw/genie-qa.txt`](evidence/raw/genie-qa.txt).

---

## 5. Deployed Databricks App — RUNNING

`databricks apps get icu-step-down`:

```
app_state:     RUNNING
compute_state: ACTIVE
url:           https://icu-step-down-7474645692590282.aws.databricksapps.com
2026-09-25T22:38:06Z [APP] INFO: Uvicorn running on http://0.0.0.0:8000
2026-09-25T22:38:08Z [APP] INFO: Application startup complete.
```

Lakebase synced tables ONLINE (`census`, `patient_features`, `census_vitals`) with
row counts read from Postgres: [`evidence/raw/lakebase-query.txt`](evidence/raw/lakebase-query.txt),
[`evidence/raw/app-deploy.txt`](evidence/raw/app-deploy.txt).

---

## 6. Enhancement evidence (drift monitoring + unit-level access)

- **Model drift job** (live, SUCCESS): `PSI 2.1528 / KS 0.2205`, verdict `drift`,
  `n_live 40` vs the training baseline, scored via UC model `readiness_model/2` —
  [`evidence/raw/drift-run.txt`](evidence/raw/drift-run.txt).
- **Derived guardrail signals** `recent_extubation` / `active_bleeding` prevalence
  across 61,532 stays — [`evidence/raw/gold-derived-signals.txt`](evidence/raw/gold-derived-signals.txt).
- **Unit-level access** (read-only, 2026-09-27): `current_user.me()` resolves the
  `icu_micu` group → scope `["MICU"]`; the scoped `WHERE care_unit IN ('MICU')`
  predicate returns **15 rows** on both `gold.census` and the Lakebase
  `mimic_iii.census` the app reads; the fail-closed `is_member()` governed view
  returns MICU-only for a non-admin — [`evidence/raw/unit-access-verification.txt`](evidence/raw/unit-access-verification.txt).

---

## How the medallion shapes MIMIC-III into readiness features

The pipeline code is in [`src/pipelines/`](src/pipelines/) (`bronze.sql`,
`silver.sql`, `gold.sql`). The gold `patient_features` row (per ICU stay) is real
feature engineering off raw clinical events, not a demographic extract:

- **Vitals aggregates** (from `silver.vital_signs`): mean/min/max/last for HR, SBP,
  DBP, SpO2, temperature, respiratory rate.
- **Labs**: `lactate_last`, plus derived `active_bleeding` (Hb drop ≥2 g/dL OR
  INR>1.5 OR platelets<50k).
- **Support flags**: `on_vasopressors`, `on_ventilator`, derived `recent_extubation`
  (vent support earlier in stay, none in the final 24h window).
- **Neuro / stay**: `gcs_last`, `los`, `age`.
- **Synthetic governance dimension**: `care_unit` (MICU/SICU/CCU).

This is the exact feature set the serving call (§3) and the app consume — one
governed gold table feeding model, app, and Genie.
