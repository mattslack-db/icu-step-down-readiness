# Phase 7A Evidence — App API: Sample JSON Responses

Date: 2026-09-08 (updated after review fixes)

**How run:**
```bash
cd /Users/matt.slack/Repos/tech-bar/app
uv run uvicorn icu_step_down.backend.app:app --host 127.0.0.1 --port 8099
# app/.env: DATABRICKS_CONFIG_PROFILE=icu-sandbox
#           PGENDPOINT=projects/icu-step-down/branches/production/endpoints/primary
#           DATABASE_NAME=databricks_postgres
```

All responses are real data from Lakebase `mimic_iii` and the live `icu-readiness` endpoint.
Data is de-identified (MIMIC-III synthetic identifiers only). No bulk raw patient rows.

---

## GET /api/census

```
curl http://127.0.0.1:8099/api/census
```

Full response: 40 patients sorted by `readiness_index` desc.
Sample below shows first 3 (highest ranked):

```json
{
  "total": 40,
  "generated_at": "2026-09-08T12:20:35.214997+00:00",
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
        {"name": "last SpO₂", "direction": "supports", "magnitude": 0.9589},
        {"name": "last lactate", "direction": "supports", "magnitude": 0.0386},
        {"name": "minimum heart rate", "direction": "supports", "magnitude": 0.0275}
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
      "icustay_id": "210785",
      "subject_id": "10510",
      "age": 21.155373,
      "los": 15.593,
      "readiness_score": 0.719658675702236,
      "readiness_index": 92,
      "band": "Ready",
      "on_vasopressors": true,
      "on_ventilator": true,
      "top_factors": [
        {"name": "last SpO₂", "direction": "supports", "magnitude": 0.5667},
        {"name": "last systolic BP", "direction": "supports", "magnitude": 0.1587},
        {"name": "age (years)", "direction": "supports", "magnitude": 0.0582}
      ]
    }
  ]
}
```

**Live census summary:** Ready 13 (32.5%) / Borderline 13 (32.5%) / Not ready 14 (35%).

---

## GET /api/patients/{icustay_id}

### Highest-ranked patient (icustay_id=287070, band=Ready)

```
curl http://127.0.0.1:8099/api/patients/287070
```

Full `vitals` array has 203 entries; first 5 shown below.

```json
{
  "features": {
    "icustay_id": "287070",
    "subject_id": "27666",
    "age": 74.628337,
    "los": 1.0841,
    "on_vasopressors": true,
    "on_ventilator": true,
    "hr_mean": 57.857142857142854,
    "sbp_mean": 125.14285714285714,
    "dbp_mean": 48.0,
    "spo2_mean": 98.44827586206897,
    "spo2_min": 100.0,
    "temp_c_mean": 35.6944448682997,
    "rr_mean": 18.125,
    "gcs_last": 15.0,
    "lactate_last": 1.1
  },
  "vitals": [
    {"charttime": "2205-08-07T16:50:00Z", "vital_name": "spo2", "value": 100.0},
    {"charttime": "2205-08-07T16:50:00Z", "vital_name": "dbp",  "value": 53.0},
    {"charttime": "2205-08-07T16:50:00Z", "vital_name": "hr",   "value": 61.0},
    {"charttime": "2205-08-07T16:50:00Z", "vital_name": "rr",   "value": 15.0},
    {"charttime": "2205-08-07T16:50:00Z", "vital_name": "dbp",  "value": 36.0}
  ],
  "readiness_score": 0.7540561316632121,
  "readiness_index": 98,
  "band": "Ready",
  "factors": [
    {"name": "last SpO₂",              "direction": "supports", "magnitude": 0.9589},
    {"name": "last lactate",            "direction": "supports", "magnitude": 0.0386},
    {"name": "minimum heart rate",      "direction": "supports", "magnitude": 0.0275},
    {"name": "minimum temperature (°C)","direction": "risk",     "magnitude": 0.0252},
    {"name": "last respiratory rate",   "direction": "supports", "magnitude": 0.0160}
  ],
  "narrative": "The patient is in the \"Ready\" band for a step-down transfer. This assessment is primarily supported by stable oxygen saturation, as evidenced by the last SpO₂, as well as favorable lactate, heart rate, and respiratory rate values. However, a slightly low minimum temperature is noted as a risk factor that warrants ongoing monitoring. Overall, the patient's clinical profile suggests they are ready for a step-down transfer, with the stable oxygenation and metabolic indicators being key supportive factors.",
  "lactate_note": "Lactate is the dominant model feature. When lactate is *measured*, even a low value signals a more complex stay; when it is *absent* (NULL), LightGBM's NaN path often indicates a quick, uncomplicated course. Interpret the lactate factor in clinical context."
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
    {"band": "Ready",      "count": 13, "pct": 32.5},
    {"band": "Borderline", "count": 13, "pct": 32.5},
    {"band": "Not ready",  "count": 14, "pct": 35.0}
  ],
  "feature_importance": [
    {"feature": "last lactate",              "importance": 0.2458},
    {"feature": "age (years)",               "importance": 0.0462},
    {"feature": "ICU length of stay (days)", "importance": 0.03491},
    {"feature": "GCS (last)",                "importance": 0.02956},
    {"feature": "last SpO₂",                 "importance": 0.02939},
    {"feature": "mean heart rate",           "importance": 0.02059},
    {"feature": "mean respiratory rate",     "importance": 0.0149},
    {"feature": "last heart rate",           "importance": 0.01404},
    {"feature": "last systolic BP",          "importance": 0.01382},
    {"feature": "mean systolic BP",          "importance": 0.01293}
  ],
  "avg_los_by_band": {
    "Not ready":  3.39,
    "Ready":      2.71,
    "Borderline": 2.34
  },
  "vent_rate": 0.275,
  "vasopressor_rate": 0.2,
  "generated_at": "2026-09-08T12:20:55.031248+00:00"
}
```

---

## Clinical Notes

**Framing:** `readiness_score` is a ranking signal (not a probability). `readiness_index`
(0–100, percentile within current census) is what the gauge and table display. Bands derived
from index: Ready ≥66, Borderline 33–65, Not ready <33.

**Lactate dominance:** Global top feature (mean |SHAP| 0.246, ~5× next). A *measured* lactate
(even low) signals complexity; NULL often indicates a quick course. The `lactate_note` field
surfaces this when lactate is a top factor for the patient.

**Direction override:** `on_vasopressors` and `on_ventilator` are always labelled `"risk"`
regardless of SHAP sign (`ALWAYS_RISK_FEATURES` in `feature_labels.py`).

**Wrong-patient-prediction fix (post-review):** The census batch query in
`/api/patients/{id}` now includes `"icustay_id"` in the SELECT; predictions are keyed
`predictions_by_id[icustay_id]` (dict lookup), not by row position. Postgres row ordering
is not guaranteed across separate unordered queries.
