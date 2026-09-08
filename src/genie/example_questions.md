# Genie Space — Curated Example Questions

These are the five sample questions configured in the ICU Step-Down Readiness Genie space. Each was validated via the Conversation API and produced correct, sensible SQL and results.

## Q1 — Current Step-Down Readiness

**Question:** How many current ICU patients are ready for step-down?

**Purpose:** Answers the primary operational question — which and how many of today's 40 census patients have a readiness_label=1 (safe to discharge from ICU). Requires a JOIN between `census` (current patients) and `readiness_training_set` (readiness outcomes).

**Expected result shape:** Three columns — `ready_for_step_down`, `not_ready`, `total_current_patients`. One row.

---

## Q2 — Length of Stay by Readiness Band

**Question:** What is the average ICU length of stay by readiness band?

**Purpose:** Shows whether bounce-back patients (label=0) and safe step-down patients (label=1) differ in ICU duration. The answer reveals whether LOS is a discriminating factor between bands.

**Expected result shape:** Two rows — one per readiness_label (0 and 1) — with `readiness_band` label, `avg_los_days`, and `num_stays`.

---

## Q3 — Vasopressors and Ventilator Overlap

**Question:** How many current patients are on vasopressors and on a ventilator at the same time?

**Purpose:** Identifies the most critically ill current patients — those on both vasopressors and mechanical ventilation simultaneously. These patients are least likely to be step-down candidates.

**Expected result shape:** Counts of `on_both`, `on_vasopressors_only`, `on_ventilator_only`, and `total_patients` from the census.

---

## Q4 — Vitals for Older Patients

**Question:** What is the average heart rate and GCS score for patients over 65?

**Purpose:** Profiles the older cohort's cardiovascular and neurological status. GCS_last and hr_mean are key step-down readiness signals; understanding age-stratified baselines helps clinical decision-making.

**Expected result shape:** `avg_heart_rate_bpm`, `avg_gcs_score`, `num_stays` — one aggregate row for the age > 65 cohort.

---

## Q5 — Bounce-Back Rate

**Question:** What fraction of ICU stays had a bounce-back within 72 hours?

**Purpose:** Surfaces the historical bounce-back rate across all 61,532 stays. Bounce-back (readiness_label=0) patients returned to the ICU within 72 hours after discharge — this rate is the base rate of incorrect step-down decisions in the dataset.

**Expected result shape:** `bounce_back_pct` (percentage), `bounce_back_count`, `total_stays` — one aggregate row.

---

## Domain Glossary (for question authors)

| Term | Meaning in this space |
|------|----------------------|
| **Step-down** | Transferring a patient from ICU to a lower-acuity ward |
| **Bounce-back** | Patient returned to ICU within 72 hours of discharge; `readiness_label = 0` |
| **Readiness band** | Grouping by `readiness_label` (1 = ready / 0 = not ready) |
| **Census** | The 40 current active ICU patients in `gold.census` |
| **GCS / gcs_last** | Glasgow Coma Scale total (3–15); 15 = fully alert, higher is better |
| **LOS** | Length of stay in DAYS (stored as string in `los` column) |
| **Readiness label** | Binary outcome: 1 = safe step-down, 0 = bounce-back. Not a probability. |
| **Vasopressors** | `on_vasopressors = true` — drugs to maintain blood pressure |
| **Ventilator** | `on_ventilator = true` — mechanical breathing support |
