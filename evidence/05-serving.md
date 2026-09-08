# Phase 5A — Serving Endpoint Status & Sample Request/Response

> **v2 — model version 2 (clean eval)**: endpoint redeployed via DABs bundle.

## Endpoint summary

| Field | Value |
|---|---|
| Name | `icu-readiness` |
| State | `READY` / `NOT_UPDATING` |
| Model | `icu_step_down.ml.readiness_model` version **2** |
| Alias | `@prod` |
| Workload size | `Small` |
| Scale-to-zero | enabled |
| Deployment method | DABs bundle (`resources/model_serving.yml`) |

The endpoint was created/updated via `databricks bundle deploy -t sandbox --profile icu-sandbox`.
The bundle YAML uses `entity_version: "2"` pointing to the registered model version produced
by the v2 training run. Alias `@prod` is set so application code can reference
`models:/icu_step_down.ml.readiness_model@prod`.

## Query format

**Endpoint**: `POST https://fe-sandbox-icu-step-down-readiness.cloud.databricks.com/serving-endpoints/icu-readiness/invocations`

**Request body**: `dataframe_records` format — one dict per patient row with all 30 FEATURE_COLS.

## Real sample request/response 1 — single patient

### Request
```json
{
  "dataframe_records": [{
    "hr_mean": 88.5, "hr_min": 72.0, "hr_max": 105.0, "hr_last": 84.0,
    "sbp_mean": 118.3, "sbp_min": 102.0, "sbp_max": 138.0, "sbp_last": 120.0,
    "dbp_mean": 68.2, "dbp_min": 58.0, "dbp_max": 80.0, "dbp_last": 70.0,
    "spo2_mean": 97.4, "spo2_min": 94.0, "spo2_max": 99.0, "spo2_last": 98.0,
    "temp_c_mean": 37.1, "temp_c_min": 36.5, "temp_c_max": 37.8, "temp_c_last": 37.2,
    "rr_mean": 16.0, "rr_min": 12.0, "rr_max": 20.0, "rr_last": 15.0,
    "on_vasopressors": 0, "on_ventilator": 0,
    "gcs_last": 15, "lactate_last": 1.1, "los": 2.5, "age": 62.5
  }]
}
```

### Response
```json
{
  "predictions": [{
    "prediction": "{\"readiness_score\": 0.46176069029012545, \"factors\": [{\"name\": \"lactate_last\", \"direction\": \"risk\", \"magnitude\": 0.27920103767956744}, {\"name\": \"los\", \"direction\": \"supports\", \"magnitude\": 0.030412835529883702}, {\"name\": \"temp_c_min\", \"direction\": \"risk\", \"magnitude\": 0.03018657048603611}, {\"name\": \"rr_mean\", \"direction\": \"supports\", \"magnitude\": 0.026985545164322416}, {\"name\": \"spo2_last\", \"direction\": \"risk\", \"magnitude\": 0.026972034314732926}]}"
  }]
}
```

## Real sample request/response 2 — two contrasting patients

### Request
```json
{
  "dataframe_records": [
    {
      "hr_mean": 68.0, "hr_min": 58.0, "hr_max": 80.0, "hr_last": 66.0,
      "sbp_mean": 122.0, "sbp_min": 112.0, "sbp_max": 135.0, "sbp_last": 120.0,
      "dbp_mean": 72.0, "dbp_min": 65.0, "dbp_max": 80.0, "dbp_last": 72.0,
      "spo2_mean": 99.0, "spo2_min": 98.0, "spo2_max": 100.0, "spo2_last": 99.0,
      "temp_c_mean": 36.8, "temp_c_min": 36.5, "temp_c_max": 37.1, "temp_c_last": 36.9,
      "rr_mean": 13.0, "rr_min": 11.0, "rr_max": 15.0, "rr_last": 12.0,
      "on_vasopressors": 0, "on_ventilator": 0,
      "gcs_last": 15, "lactate_last": 0.4, "los": 1.0, "age": 38.0
    },
    {
      "hr_mean": 110.0, "hr_min": 95.0, "hr_max": 130.0, "hr_last": 115.0,
      "sbp_mean": 88.0, "sbp_min": 72.0, "sbp_max": 100.0, "sbp_last": 85.0,
      "dbp_mean": 52.0, "dbp_min": 42.0, "dbp_max": 62.0, "dbp_last": 50.0,
      "spo2_mean": 91.0, "spo2_min": 86.0, "spo2_max": 95.0, "spo2_last": 88.0,
      "temp_c_mean": 38.9, "temp_c_min": 38.2, "temp_c_max": 39.5, "temp_c_last": 39.2,
      "rr_mean": 24.0, "rr_min": 20.0, "rr_max": 30.0, "rr_last": 26.0,
      "on_vasopressors": 1, "on_ventilator": 1,
      "gcs_last": 8, "lactate_last": 6.2, "los": 7.5, "age": 78.0
    }
  ]
}
```

### Response
```json
{
  "predictions": [
    {
      "prediction": "{\"readiness_score\": 0.5262129781262446, \"factors\": [{\"name\": \"lactate_last\", \"direction\": \"risk\", \"magnitude\": 0.21225860789450382}, {\"name\": \"age\", \"direction\": \"supports\", \"magnitude\": 0.16402361662137746}, {\"name\": \"rr_last\", \"direction\": \"supports\", \"magnitude\": 0.06620151729138346}, {\"name\": \"on_ventilator\", \"direction\": \"risk\", \"magnitude\": 0.029775666674647674}, {\"name\": \"spo2_last\", \"direction\": \"risk\", \"magnitude\": 0.02438518442949537}]}"
    },
    {
      "prediction": "{\"readiness_score\": 0.44361507823076346, \"factors\": [{\"name\": \"lactate_last\", \"direction\": \"risk\", \"magnitude\": 0.2261717622648495}, {\"name\": \"rr_min\", \"direction\": \"risk\", \"magnitude\": 0.11120902604512867}, {\"name\": \"spo2_last\", \"direction\": \"supports\", \"magnitude\": 0.1058198567379225}, {\"name\": \"hr_last\", \"direction\": \"risk\", \"magnitude\": 0.07229505553227629}, {\"name\": \"los\", \"direction\": \"risk\", \"magnitude\": 0.03347291598173252}]}"
    }
  ]
}
```

**Clinical ordering (v2)**: healthy young patient (score=0.526) > critically ill (score=0.444) —
correct direction. v1 had this inverted due to eval-set leak.

## Endpoint infrastructure

- Serving endpoint created and managed by DABs bundle (`resources/model_serving.yml`)
- Serving entity: `icu_step_down.ml.readiness_model`, version `2`
- Traffic: 100% to `readiness_model-2`
- Verified `state.ready == "READY"` and `state.config_update == "NOT_UPDATING"` before querying
- Scale-to-zero enabled; first query after idle period will have cold-start latency (~30s)
- `.ipynb` files excluded from bundle sync via `databricks.yml` `sync.exclude` to avoid conflict with `.py` notebooks

## Consuming the endpoint (app / narrative)

The outer `prediction` field is a JSON string — parse it before use:

```python
import json, requests

response = requests.post(
    "https://fe-sandbox-icu-step-down-readiness.cloud.databricks.com"
    "/serving-endpoints/icu-readiness/invocations",
    headers={"Authorization": f"Bearer {token}"},
    json={"dataframe_records": [feature_row]},
)
raw = response.json()["predictions"][0]["prediction"]
result = json.loads(raw)
score = result["readiness_score"]   # float; class-weight compression → ~0.44–0.97 range
factors = result["factors"]          # list of {name, direction, magnitude}
```

**Factor interface** (matches Phase 5B `Factor(name, direction, magnitude)`):
- `name`: feature name from FEATURE_COLS
- `direction`: `"supports"` (SHAP > 0, pushes toward safe step-down) or `"risk"` (SHAP < 0)
- `magnitude`: absolute SHAP value (higher = more influential)
- Returns top-5 by magnitude

**Missing-column guard**: if any of the 30 FEATURE_COLS are absent, `ReadinessModel.predict`
raises `ValueError` naming the missing columns — no silent KeyError.

## Notes on re-deployment

To update after retraining:
1. Retrain — new version registered to `icu_step_down.ml.readiness_model`
2. Set alias: `client.set_registered_model_alias(FULL_NAME, "prod", new_version)`
3. Update `resources/model_serving.yml` — `entity_version` and `served_model_name`
4. Re-run `databricks bundle deploy -t sandbox --profile icu-sandbox`
