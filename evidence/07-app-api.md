# Phase 7A Evidence — App API: Sample JSON Responses

Date: 2026-09-08

How run: direct `uvicorn` against the icu-sandbox workspace using the
`DATABRICKS_CONFIG_PROFILE=icu-sandbox` profile in `app/.env`.  No APX dev tunnel needed.
Responses are real data from Lakebase `mimic_iii` and the live `icu-readiness` serving endpoint.

```bash
cd /Users/matt.slack/Repos/tech-bar/app
uv run uvicorn icu_step_down.backend.app:app --host 127.0.0.1 --port 8099
```

All responses de-identified (MIMIC-III synthetic identifiers only).

---

## GET /api/census

```
curl http://127.0.0.1:8099/api/census
```

Response (40 patients, first 3 shown, sorted by readiness_index desc):

```json
{
  "total": 40,
  "generated_at": "2026-09-08T12:08:08.653264+00:00",
  "patients": [
    {
      "icustay_id": "287070",
      "subject_id": "27666",
      "age": 74.628337,
      "los": 1.0841,
      "readiness_score": 0.7540561316632121,
      "readiness_index": 98,
      "band": "Ready",
      "on_vasopressors": true,
      "on_ventilator": true,
      "top_factors": [
        {"name": "last SpO₂", "direction": "supports", "magnitude": 0.9589212267922425},
        {"name": "last lactate", "direction": "supports", "magnitude": 0.03862350672985439},
        {"name": "minimum heart rate", "direction": "supports", "magnitude": 0.02752916589960416}
      ]
    },
    {
      "icustay_id": "272431",
      "subject_id": "19191",
      "age": 80.851472,
      "los": 0.9195,
      "readiness_score": 0.745746431073342,
      "readiness_index": 95,
      "band": "Ready",
      "on_vasopressors": true,
      "on_ventilator": false,
      "top_factors": [
        {"name": "GCS (last)", "direction": "supports", "magnitude": 0.5417},
        {"name": "last systolic BP", "direction": "supports", "magnitude": 0.3194},
        {"name": "last SpO₂", "direction": "supports", "magnitude": 0.0440}
      ]
    },
    {
      "icustay_id": "290671",
      "subject_id": "22557",
      "age": 81.478439,
      "los": 3.0077,
      "readiness_score": 0.40155240458650737,
      "readiness_index": 0,
      "band": "Not ready",
      "on_vasopressors": false,
      "on_ventilator": false,
      "top_factors": [
        {"name": "last lactate", "direction": "risk", "magnitude": 0.2769},
        {"name": "age (years)", "direction": "risk", "magnitude": 0.1015},
        {"name": "last heart rate", "direction": "risk", "magnitude": 0.0661}
      ]
    }
  ]
}
```

**Band distribution (live census):**
- Ready: 13 (32.5 %)
- Borderline: 13 (32.5 %)
- Not ready: 14 (35.0 %)

---

## GET /api/patients/{icustay_id}

### Highest-ranked patient (icustay_id=287070)

```
curl http://127.0.0.1:8099/api/patients/287070
```

```json
{
  "features": {
    "icustay_id": "287070",
    "subject_id": "27666",
    "age": 74.628337,
    "los": 1.0841,
    "on_vasopressors": true,
    "on_ventilator": true,
    "hr_mean": 57.857,
    "sbp_mean": 125.143,
    "dbp_mean": 48.0,
    "spo2_mean": 98.448,
    "spo2_min": 100.0,
    "temp_c_mean": 35.694,
    "rr_mean": 18.125,
    "gcs_last": 15.0,
    "lactate_last": 1.1
  },
  "readiness_score": 0.7540561316632121,
  "readiness_index": 98,
  "band": "Ready",
  "factors": [
    {"name": "last SpO₂", "direction": "supports", "magnitude": 0.9589},
    {"name": "last lactate", "direction": "supports", "magnitude": 0.0386},
    {"name": "minimum heart rate", "direction": "supports", "magnitude": 0.0275},
    {"name": "minimum temperature (°C)", "direction": "risk", "magnitude": 0.0252},
    {"name": "last respiratory rate", "direction": "supports", "magnitude": 0.0160}
  ],
  "narrative": "The patient is in the \"Ready\" band for a step-down transfer. This decision is primarily supported by stable oxygen saturation, as evidenced by the last SpO₂, as well as favorable lactate and heart rate levels. While the patient's minimum temperature poses a slight risk, the overall clinical picture suggests readiness for transfer, with additional supportive factors including a stable respiratory rate. The patient's stable vital signs and laboratory values indicate a low-risk profile for step-down transfer.",
  "lactate_note": "Lactate is the dominant model feature. When lactate is *measured*, even a low value signals a more complex stay; when it is *absent* (NULL), LightGBM's NaN path often indicates a quick, uncomplicated course. Interpret the lactate factor in clinical context.",
  "vitals": [
    {"charttime": "2181-05-10T22:41:00Z", "vital_name": "hr",   "value": 54.0},
    {"charttime": "2181-05-10T22:41:00Z", "vital_name": "sbp",  "value": 152.0},
    {"charttime": "2181-05-10T22:41:00Z", "vital_name": "dbp",  "value": 49.0},
    {"charttime": "2181-05-10T22:41:00Z", "vital_name": "spo2", "value": 99.0},
    {"charttime": "2181-05-10T22:41:00Z", "vital_name": "rr",   "value": 17.0}
  ],
  "vitals_count_total": 203
}
```

### Lowest-ranked patient (icustay_id=290671)

```
curl http://127.0.0.1:8099/api/patients/290671
```

```json
{
  "features": {
    "icustay_id": "290671",
    "subject_id": "22557",
    "age": 81.478439,
    "los": 3.0077,
    "on_vasopressors": false,
    "on_ventilator": false,
    "hr_mean": 107.826,
    "sbp_mean": 99.273,
    "dbp_mean": 55.682,
    "spo2_mean": 98.167,
    "spo2_min": 100.0,
    "temp_c_mean": 36.278,
    "rr_mean": 20.0,
    "gcs_last": 15.0,
    "lactate_last": 0.6
  },
  "readiness_score": 0.40155240458650737,
  "readiness_index": 0,
  "band": "Not ready",
  "factors": [
    {"name": "last lactate", "direction": "risk", "magnitude": 0.2769},
    {"name": "age (years)", "direction": "risk", "magnitude": 0.1015},
    {"name": "last heart rate", "direction": "risk", "magnitude": 0.0661},
    {"name": "last SpO₂", "direction": "risk", "magnitude": 0.0322},
    {"name": "mean temperature (°C)", "direction": "risk", "magnitude": 0.0271}
  ],
  "narrative": "The patient is currently not ready for a step-down transfer. The primary concerns are elevated lactate levels, advanced age, and tachycardia, which collectively suggest ongoing instability and increased risk. Additionally, suboptimal oxygen saturation and temperature regulation contribute to the patient's unreadiness, although to a lesser extent. These factors indicate a need for continued intensive care and close monitoring before considering a transfer to a lower level of care.",
  "lactate_note": "Lactate is the dominant model feature. When lactate is *measured*, even a low value signals a more complex stay; when it is *absent* (NULL), LightGBM's NaN path often indicates a quick, uncomplicated course. Interpret the lactate factor in clinical context.",
  "vitals": [
    {"charttime": "2203-09-26T12:30:00Z", "vital_name": "dbp",  "value": 59.0},
    {"charttime": "2203-09-26T12:30:00Z", "vital_name": "hr",   "value": 102.0},
    {"charttime": "2203-09-26T12:30:00Z", "vital_name": "rr",   "value": 25.0},
    {"charttime": "2203-09-26T12:30:00Z", "vital_name": "sbp",  "value": 109.0},
    {"charttime": "2203-09-26T12:30:00Z", "vital_name": "spo2", "value": 99.0}
  ],
  "vitals_count_total": 403
}
```

---

## GET /api/analytics

```
curl http://127.0.0.1:8099/api/analytics
```

```json
{
  "total_census": 40,
  "band_distribution": [
    {"band": "Ready", "count": 13, "pct": 32.5},
    {"band": "Borderline", "count": 13, "pct": 32.5},
    {"band": "Not ready", "count": 14, "pct": 35.0}
  ],
  "feature_importance": [
    {"feature": "last lactate", "importance": 0.2458},
    {"feature": "age (years)", "importance": 0.0462},
    {"feature": "ICU length of stay (days)", "importance": 0.03491},
    {"feature": "GCS (last)", "importance": 0.02956},
    {"feature": "last SpO₂", "importance": 0.02939},
    {"feature": "mean heart rate", "importance": 0.02059},
    {"feature": "mean respiratory rate", "importance": 0.0149},
    {"feature": "last heart rate", "importance": 0.01404},
    {"feature": "last systolic BP", "importance": 0.01382},
    {"feature": "mean systolic BP", "importance": 0.01293}
  ],
  "avg_los_by_band": {
    "Not ready": 3.39,
    "Ready": 2.71,
    "Borderline": 2.34
  },
  "vent_rate": 0.275,
  "vasopressor_rate": 0.2,
  "generated_at": "2026-09-08T12:07:26.455844+00:00"
}
```

---

## Clinical Notes

### Framing
- `readiness_score` is a RANKING signal (raw values ~0.40–0.75 in this census; normal range is ~0.44–0.53 but outliers exist).
- `readiness_index` is the percentile rank within the current census (0–100). This is what the gauge and ranking table display.
- Bands are derived from `readiness_index` (not raw score): Ready ≥66, Borderline 33–65, Not ready <33.

### Lactate dominance
The model's top global feature is `lactate_last` (mean |SHAP| = 0.246, ~5× the next feature). A *measured* lactate (even low) signals a more complex stay; a NULL lactate often indicates a quick safe course. The `lactate_note` field in `/api/patients/{id}` surfaces this whenever lactate appears in the top factors.

### On-vasopressors / on-ventilator direction fix
The `ALWAYS_RISK_FEATURES` set in `feature_labels.py` ensures `on_vasopressors` and `on_ventilator` are always labelled as "risk" direction, regardless of the raw SHAP sign — clinical correctness override.
