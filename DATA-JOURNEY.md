# Data Journey — raw MIMIC-III → governed gold features → Genie

This file makes the **medallion transformation logic** and the **Genie space
configuration** readable end to end in one place, without descending into
`src/`. The authoritative source is [`src/pipelines/`](src/pipelines/)
(`bronze.sql`, `silver.sql`, `gold.sql`) and [`src/genie/`](src/genie/)
(`space_config.md`, `example_questions.md`, `genie_agent.json`); the meaningful
transformations are reproduced below verbatim. Run output that proves it
executed is in [`EVIDENCE.md`](EVIDENCE.md).

```
MIMIC-III (Delta Share)
  → bronze  (raw tables as materialized views)
  → silver  (typed, cleaned, vitals unpivoted, lab flags)
  → gold    (24h feature engineering: patient_features → readiness_training_set + census)
  → Genie / model serving / app
```

---

## Bronze — raw MIMIC-III ingested as materialized views

`src/pipelines/bronze.sql` reads the Delta-shared MIMIC-III tables and lands
them as UC materialized views (no transformation): `patients`, `admissions`,
`icu_stays`, `transfers`, `services`, `prescriptions`, `chart_events`,
`lab_events`, `input_events_mv`, `input_events_cv`, `procedure_events_mv`,
`d_labitems`. Row counts (live run): `chart_events 38,776,289`,
`lab_events 27,854,055`, `icu_stays 61,532`, `admissions 58,976` — see EVIDENCE.md §1.

---

## Silver — typing, cleaning, and the vitals unpivot

The core silver transformation turns wide `chart_events` (one column per
measurement type, keyed by `ITEMID`) into a long, typed `vital_signs` stream
with unit normalization and physiologic range filtering
(`src/pipelines/silver.sql`):

```sql
CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.silver.vital_signs AS
-- map raw MIMIC ITEMIDs to a canonical vital_name
SELECT ... 
  CASE
    WHEN ITEMID IN (211, 220045)                            THEN 'hr'
    WHEN ITEMID IN (51, 442, 455, 6701, 220179, 220050)     THEN 'sbp'
    WHEN ITEMID IN (8368, 8440, 8441, 8555, 220180, 220051) THEN 'dbp'
    WHEN ITEMID IN (646, 220277)                            THEN 'spo2'
    WHEN ITEMID IN (678, 223761, 676, 223762)               THEN 'temp_c'
    WHEN ITEMID IN (615, 618, 220210, 224690)               THEN 'rr'
  END AS vital_name,
  CASE
    WHEN ITEMID IN (678, 223761) THEN (VALUENUM - 32.0) * 5.0 / 9.0  -- °F → °C
    ELSE VALUENUM
  END AS value
FROM icu_step_down.bronze.chart_events
-- (GCS assembled from its own ITEMID paths in a UNION branch)
...
WHERE vital_name IS NOT NULL
  AND (   (vital_name = 'hr'     AND value BETWEEN 20 AND 250)
       OR (vital_name = 'sbp'    AND value BETWEEN 50 AND 300)
       OR (vital_name = 'dbp'    AND value BETWEEN 20 AND 200)
       OR (vital_name = 'spo2'   AND value BETWEEN 50 AND 100)
       OR (vital_name = 'temp_c' AND value BETWEEN 30 AND 43)
       OR (vital_name = 'rr'     AND value BETWEEN 4  AND 60) );
```

`silver.lab_events` carries a derived `is_lactate` flag (`ITEMID = 50813`);
`silver.patients` and `silver.icu_stays` are typed/cleaned projections of their
bronze sources. Result: `silver.vital_signs` = 21,771,413 typed readings.

---

## Gold — 24-hour feature engineering (`gold.patient_features`)

`gold.patient_features` (one row per ICU stay) is the governed feature set the
model, app, and Genie all consume. Real logic from `src/pipelines/gold.sql`:

```sql
-- 24-hour window ending at discharge (or intime + 1 day if still in unit)
stay_windows AS (
  SELECT icustay_id, subject_id, hadm_id, intime, outtime, los,
    COALESCE(outtime, intime + INTERVAL 1 DAY)                  AS window_end,
    COALESCE(outtime, intime + INTERVAL 1 DAY) - INTERVAL 1 DAY AS window_start
  FROM icu_step_down.silver.icu_stays
),
-- rank readings within the window so we can take mean/min/max AND last
vitals_window AS (
  SELECT sw.icustay_id, v.vital_name, v.value, v.charttime,
    ROW_NUMBER() OVER (PARTITION BY sw.icustay_id, v.vital_name
                       ORDER BY v.charttime DESC) AS rn
  FROM stay_windows sw
  JOIN icu_step_down.silver.vital_signs v
    ON v.icustay_id = sw.icustay_id
   AND v.charttime >= sw.window_start AND v.charttime < sw.window_end
),
-- aggregate: mean/min/max over the window + last (rn = 1) per vital
vitals_agg AS (
  SELECT icustay_id,
    AVG(CASE WHEN vital_name='hr' THEN value END)              AS hr_mean,
    MAX(CASE WHEN vital_name='hr'  AND rn=1 THEN value END)     AS hr_last,
    ... (sbp, dbp, spo2, temp_c, rr: mean/min/max/last) ...
    MAX(CASE WHEN vital_name='gcs' AND rn=1 THEN value END)     AS gcs_last
  FROM vitals_window GROUP BY icustay_id
),
```

Support flags are derived from the intervention tables by clinical `ITEMID`
sets, unioning MetaVision + CareVue sources:

```sql
-- on_vasopressors: any vasopressor infusion during the stay (MV or CV itemids)
vasopressor_mv AS (SELECT DISTINCT ICUSTAY_ID FROM icu_step_down.bronze.input_events_mv
                   WHERE ITEMID IN (221906,221289,221662,221653,222315,221749)),
vasopressor_cv AS (SELECT DISTINCT ICUSTAY_ID FROM icu_step_down.bronze.input_events_cv
                   WHERE ITEMID IN (30047,30112,30044,30119,30043,30307,30042,30051,30128)),
-- on_ventilator: procedure_events_mv OR ventilator-mode chart_events
ventilator AS (SELECT ICUSTAY_ID FROM icu_step_down.bronze.procedure_events_mv
                 WHERE ITEMID IN (225792,225794,224385)
               UNION SELECT ICUSTAY_ID FROM icu_step_down.bronze.chart_events
                 WHERE ITEMID IN (720,722,223849)),
-- lactate_last: most recent lactate during the stay
lactate AS (SELECT hadm_id, ... QUALIFY ROW_NUMBER() OVER
              (PARTITION BY hadm_id ORDER BY charttime DESC) = 1
            FROM icu_step_down.silver.lab_events WHERE is_lactate = TRUE),
```

Two clinical **guardrail signals** are derived in the same view:

- `recent_extubation` — had ventilator support in the stay but none in the final
  24h window (a vent-off transition).
- `active_bleeding` — Hb drop ≥ 2 g/dL in the window **OR** coagulopathy
  (INR > 1.5 or platelets < 50k).

And a synthetic governance dimension:

```sql
CASE pmod(CAST(sw.icustay_id AS BIGINT), 3)
  WHEN 0 THEN 'MICU' WHEN 1 THEN 'SICU' ELSE 'CCU'
END AS care_unit   -- synthetic (de-identified data); stable across re-runs
```

### Gold outputs built on `patient_features`

- **`gold.readiness_training_set`** = `patient_features` + `readiness_label`
  (1 = safe step-down, 0 = returned to ICU within 72h). 61,532 rows;
  59,706 ready / 1,826 bounce-back.
- **`gold.census`** = the 40 current ICU patients (`SELECT pf.*`), so `care_unit`
  and the guardrail signals propagate automatically.

One governed gold feature set → the serving model, the app, and Genie all read
the same lineage.

---

## Genie space configuration

Full config in [`src/genie/space_config.md`](src/genie/space_config.md);
serialized definition in `src/genie/genie_agent.json`. Summary:

- **Title:** ICU Step-Down Readiness · **Warehouse:** Serverless Starter.
- **Tables exposed (3):** `gold.census` (40 current), `gold.readiness_training_set`
  (61,532 historical + outcome label), `silver.vital_signs` (21.7M time-series).
  `patient_features` is intentionally excluded (it is a subset of
  `readiness_training_set`, which would confuse table selection).
- **Text instructions** cover: disambiguation ("current patients" → `census`;
  historical/aggregate → `readiness_training_set`; "bounce-back" = readiness_label
  0 within 72h; GCS is the 3–15 total; `los` is days-as-string → `CAST(... AS DOUBLE)`),
  data-quality notes (NULL vital rates, the 21.7M-row filter rule), and
  constraints (aggregates only, no `SELECT *`, no individual patient rows).
- **Five configured example questions**, e.g.:

```sql
-- "How many current ICU patients are ready for step-down?"
SELECT SUM(CASE WHEN r.readiness_label = 1 THEN 1 ELSE 0 END) AS ready_for_step_down,
       SUM(CASE WHEN r.readiness_label = 0 THEN 1 ELSE 0 END) AS not_ready,
       COUNT(*) AS total_current_patients
FROM icu_step_down.gold.census c
JOIN icu_step_down.gold.readiness_training_set r ON c.icustay_id = r.icustay_id;
-- live result: ready=38, not_ready=2, total=40  (see EVIDENCE.md §4)
```

Live natural-language Q&A (question → generated SQL → rows) is captured in
[`evidence/raw/genie-qa.txt`](evidence/raw/genie-qa.txt).
