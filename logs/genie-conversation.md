# Genie conversation — live Q&A over the governed tables

Captured 2026-09-25 via the Genie Conversation API (space
`01f1b92aeef914e383e43c1452d294cf`, profile `icu-sandbox`). Each question →
Genie-generated SQL → result rows. Full transcript (all 5 turns) in
[`../evidence/raw/genie-qa.txt`](../evidence/raw/genie-qa.txt).

---

**Q1 — "How many current ICU patients are ready for step-down?"**

```sql
SELECT SUM(CASE WHEN r.readiness_label = 1 THEN 1 ELSE 0 END) AS ready_for_step_down,
       SUM(CASE WHEN r.readiness_label = 0 THEN 1 ELSE 0 END) AS not_ready,
       COUNT(*) AS total_current_patients
FROM icu_step_down.gold.census c
JOIN icu_step_down.gold.readiness_training_set r ON c.icustay_id = r.icustay_id
```
**Result:** `ready_for_step_down=38, not_ready=2, total_current_patients=40`

---

**Q2 — "What is the average ICU length of stay by readiness band?"**

**Result:** Not ready → `avg_los_days=4.87` (n=1,816); Ready → `avg_los_days=4.92` (n=59,706)

---

**Q3 — "How many current patients are on vasopressors and a ventilator at the same time?"**

```sql
SELECT SUM(CASE WHEN on_vasopressors AND on_ventilator THEN 1 ELSE 0 END) AS on_both,
       SUM(CASE WHEN on_vasopressors THEN 1 ELSE 0 END) AS on_vasopressors,
       SUM(CASE WHEN on_ventilator THEN 1 ELSE 0 END) AS on_ventilator,
       COUNT(*) AS total_patients
FROM icu_step_down.gold.census
```
**Result:** `on_both=5, on_vasopressors=8, on_ventilator=11, total_patients=40`

---

**Q4 — "What is the average heart rate and GCS for patients over 65?"**

**Result:** `avg_heart_rate_bpm=81.5, avg_gcs_score=13.4, num_stays=14,812`

---

**Q5 — "What fraction of ICU stays had a bounce-back within 72 hours?"**

**Result:** `bounce_back_pct=2.97, bounce_back_count=1,826, total_stays=61,532`
