# ICU Step-Down Readiness App - Complete Specification

## Executive Summary

**Purpose:** Help ICU clinicians identify which patients are ready to be safely transferred from intensive care to step-down units, freeing up ICU beds for critical patients while ensuring patient safety.

**Impact:** Reduces ICU overcrowding, optimizes bed utilization, improves patient flow, and supports clinical decision-making with AI-powered risk assessment.

**Technology Stack:** Databricks App (React), ML model deployed via Mosaic AI, real-time data from Lakebase

---

## 1. Business Problem & Value Proposition

### The Challenge
- **ICU Bed Scarcity:** ICUs operate at 70-90% capacity; one blocked bed can delay critical admissions
- **Conservative Transfers:** Clinicians often delay step-down transfers due to fear of readmission
- **Manual Assessment:** Current evaluation is subjective and time-consuming
- **Variability:** Discharge decisions vary by provider, shift, and hospital

### The Solution
AI-powered app that:
1. **Predicts** which patients can safely step down in next 24-48 hours
2. **Ranks** all ICU patients by readiness score
3. **Explains** key factors driving each recommendation
4. **Tracks** outcomes to continuously improve predictions

### Value Delivered
- **Operational:** 10-15% reduction in ICU length of stay
- **Financial:** $2,000-5,000 saved per day per accelerated discharge
- **Clinical:** Reduced ICU readmissions through better patient selection
- **Capacity:** More ICU beds available for emergency admissions

---

## 2. Data Sources & Schema

- All the data is stored in Lakebase. 
- Lakebase (Postgres) column names are case sensitive, you need to change the queries to upper case.
- The profile to use is fe-vm.
- The Lakebase instance is called icu-step-down.
- The tables in this instance are all in a catalog called mimic_iii.mimic_iii.
- They are described in 01-source-data.md.

---

## 3. App User Interface Design

### Landing Page: ICU Census Dashboard

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  ICU Step-Down Readiness Dashboard      [Refresh] [Settings]│
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Summary Metrics (Cards)                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │Total ICU │  │Ready for │  │Borderline│  │Not Ready │    │
│  │Patients  │  │Step-Down │  │Cases     │  │          │    │
│  │   24     │  │    7     │  │    5     │  │    12    │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ ICU Bed Utilization                                   │   │
│  │ ████████████████████████░░░░░░  80% (24/30 beds)     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Patient List (Sortable Table)                               │
│  ┌─────┬─────────┬────┬─────┬──────────┬─────────────┬────┐│
│  │Rank │Patient  │Age │LOS  │Readiness │Key Factors  │Act.││
│  ├─────┼─────────┼────┼─────┼──────────┼─────────────┼────┤│
│  │🟢 1 │Smith, J │67  │3.2d │   92%    │✓Stable VS   │[→] ││
│  │     │RM 412   │    │     │ READY    │✓Off pressors│    ││
│  ├─────┼─────────┼────┼─────┼──────────┼─────────────┼────┤│
│  │🟢 2 │Jones, M │54  │5.1d │   88%    │✓Extubated   │[→] ││
│  │     │RM 408   │    │     │ READY    │⚠ High HR    │    ││
│  ├─────┼─────────┼────┼─────┼──────────┼─────────────┼────┤│
│  │🟡 3 │Davis, P │72  │2.8d │   68%    │⚠ Lactate ↑  │[→] ││
│  │     │RM 415   │    │     │BORDERLINE│✓GCS normal  │    ││
│  ├─────┼─────────┼────┼─────┼──────────┼─────────────┼────┤│
│  │🔴 4 │Wilson,K │81  │1.2d │   15%    │✗On vent     │[→] ││
│  │     │RM 402   │    │     │NOT READY │✗On pressors │    ││
│  └─────┴─────────┴────┴─────┴──────────┴─────────────┴────┘│
└─────────────────────────────────────────────────────────────┘
```

**Color Coding:**
- 🟢 Green (>75%): Ready for step-down
- 🟡 Yellow (50-75%): Borderline, needs clinical judgment
- 🔴 Red (<50%): Not ready, requires continued ICU care

**Sorting Options:**
- Readiness Score (default)
- ICU Length of Stay
- Age
- Admission Time
- Custom filters (by unit, diagnosis, etc.)

---

### Patient Detail View

**Clicked from table row:**
```
┌─────────────────────────────────────────────────────────────┐
│  ← Back to Dashboard                    Patient: Smith, John │
│                                          MRN: 12345 | Age: 67│
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Step-Down Readiness Assessment                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                                                       │    │
│  │            READY FOR STEP-DOWN                        │    │
│  │                    92%                                │    │
│  │         ████████████████████░                         │    │
│  │                                                       │    │
│  │  Confidence: High | Last Updated: 11/29/2025 14:30   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  Top Factors Supporting Transfer                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ ✅ Hemodynamically stable (off vasopressors 36h)     │    │
│  │ ✅ Respiratory: SpO2 >95% on 2L NC                   │    │
│  │ ✅ Neurologically intact (GCS 15)                    │    │
│  │ ✅ Improving trend in vital signs                    │    │
│  │ ✅ No active bleeding or coagulopathy                │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  Risk Factors / Cautions                                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ ⚠️  Mild tachycardia (HR 95-105) - monitor          │    │
│  │ ⚠️  Recent extubation (18h ago) - watch for fatigue │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  Clinical Summary Tabs                                        │
│  ┌─────┬──────────┬──────┬─────────┬───────────┐           │
│  │Vital│Labs      │Meds  │Trends   │History    │           │
│  │Signs│          │      │         │           │           │
│  └─────┴──────────┴──────┴─────────┴───────────┘           │
│                                                               │
│  [Tab: Vital Signs - Last 24 Hours]                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Heart Rate Chart                                    │    │
│  │  120├─────────────────────────────────────          │    │
│  │  100├─────────●●●●●●●●──────────────────          │    │
│  │   80├───────────────────────────────────          │    │
│  │   60├─────────────────────────────────────          │    │
│  │      0h    6h    12h   18h   24h                    │    │
│  │                                                       │    │
│  │  Blood Pressure: 128/76 (stable)                    │    │
│  │  SpO2: 97% on 2L O2                                 │    │
│  │  Temperature: 37.2°C                                │    │
│  │  Respiratory Rate: 16                               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  Recommended Actions                                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 📋 Consider step-down transfer within next 4-8 hours│    │
│  │ 🔔 Monitor HR trend - reassess if >110 sustained    │    │
│  │ 💊 Review if pain medications can be transitioned   │    │
│  │    from IV to PO                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  [Mark as Transferred] [Override Score] [Add Note]           │
└─────────────────────────────────────────────────────────────┘
```

---

### Trends & Analytics View

**Tab in main navigation:**
```
┌─────────────────────────────────────────────────────────────┐
│  Analytics & Trends                                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Model Performance Metrics (This Month)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │Prediction│  │False     │  │ICU       │  │Average   │    │
│  │Accuracy  │  │Positives │  │Readmit   │  │LOS Saved │    │
│  │   87%    │  │   5%     │  │Rate      │  │  0.8 days│    │
│  │          │  │          │  │   3.2%   │  │          │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│                                                               │
│  Transfers Over Time                                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  30│                                                 │    │
│  │  25├──────●──────────────────                       │    │
│  │  20├────────────●────●──────────                    │    │
│  │  15├──────────────────────●──────                   │    │
│  │  10├────────────────────────────●                   │    │
│  │   5├─────────────────────────────────●             │    │
│  │    └────────────────────────────────────            │    │
│  │     Week 1  Week 2  Week 3  Week 4                  │    │
│  │                                                       │    │
│  │  ━━━ AI-Recommended  ━━━ Manual Decisions           │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  Feature Importance (What Drives Predictions)                │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Vasopressor Status      ████████████████ 34%      │    │
│  │  GCS Score              ██████████████ 28%         │    │
│  │  Lactate Trend          ████████ 16%               │    │
│  │  Respiratory Support     ██████ 12%                 │    │
│  │  Age                    ████ 6%                    │    │
│  │  Other                  ██ 4%                      │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Appendix

### Sample SQL Queries

```sql
-- Get patients ready for step-down
SELECT 
    p.subject_id,
    i.icustay_id,
    p.gender,
    YEAR(CURRENT_DATE) - YEAR(p.dob) as age,
    i.los,
    f.readiness_score,
    f.hr_24h_mean,
    f.bp_systolic_24h_mean,
    f.on_vasopressors,
    f.on_ventilator
FROM patients p
JOIN icustays i ON p.subject_id = i.subject_id
JOIN gold_patient_features f ON i.icustay_id = f.icustay_id
WHERE i.outtime IS NULL  -- Currently in ICU
  AND f.readiness_score >= 0.75
ORDER BY f.readiness_score DESC;

-- Get vital signs trend for a patient
SELECT 
    charttime,
    hr,
    sbp,
    dbp,
    spo2,
    temp
FROM silver_vital_signs
WHERE icustay_id = 12345
  AND charttime >= CURRENT_TIMESTAMP - INTERVAL 24 HOURS
ORDER BY charttime;
```

### Useful Links

- MIMIC-III Documentation: https://mimic.mit.edu/docs/iii/
- Databricks Apps Guide: https://docs.databricks.com/apps/
- MLflow Model Registry: https://mlflow.org/docs/latest/model-registry.html
- SHAP Documentation: https://shap.readthedocs.io/

---

**End of Specification**

This comprehensive spec provides everything needed to build a production-ready ICU Step-Down Readiness App on Databricks!
