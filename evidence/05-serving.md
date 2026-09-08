# Phase 5A — Serving Endpoint Status & Sample Request/Response

## Endpoint summary

| Field | Value |
|---|---|
| Name | `icu-readiness` |
| State | `READY` / `NOT_UPDATING` |
| Model | `icu_step_down.ml.readiness_model` version `1` |
| Alias | `@prod` |
| Workload size | `Small` |
| Scale-to-zero | enabled |
| Deployment method | DABs bundle (`resources/model_serving.yml`) |

The endpoint was created via `databricks bundle deploy -t sandbox --profile icu-sandbox`.
The bundle YAML uses `entity_version: "1"` pointing to the registered model version
produced by the training notebook. Alias `@prod` is also set so application code can
reference `models:/icu_step_down.ml.readiness_model@prod`.

## Query format

**Endpoint**: `POST https://fe-sandbox-icu-step-down-readiness.cloud.databricks.com/serving-endpoints/icu-readiness/invocations`

**Request body**: `dataframe_records` format — one dict per patient row.

```json
{
  "dataframe_records": [
    {
      "hr_mean": 88.5,
      "hr_min": 72.0,
      "hr_max": 105.0,
      "hr_last": 84.0,
      "sbp_mean": 118.3,
      "sbp_min": 102.0,
      "sbp_max": 138.0,
      "sbp_last": 120.0,
      "dbp_mean": 68.2,
      "dbp_min": 58.0,
      "dbp_max": 80.0,
      "dbp_last": 70.0,
      "spo2_mean": 97.4,
      "spo2_min": 94.0,
      "spo2_max": 99.0,
      "spo2_last": 98.0,
      "temp_c_mean": 37.1,
      "temp_c_min": 36.5,
      "temp_c_max": 37.8,
      "temp_c_last": 37.2,
      "rr_mean": 16.0,
      "rr_min": 12.0,
      "rr_max": 20.0,
      "rr_last": 15.0,
      "on_vasopressors": 0,
      "on_ventilator": 0,
      "gcs_last": 15,
      "lactate_last": 1.1,
      "los": 2.5,
      "age": 62.5
    }
  ]
}
```

**Response**:
```json
{
  "predictions": [
    {
      "prediction": "{\"readiness_score\": 0.4447135290222422, \"factors\": [{\"name\": \"lactate_last\", \"direction\": \"risk\", \"magnitude\": 0.3557688611235546}, {\"name\": \"on_ventilator\", \"direction\": \"risk\", \"magnitude\": 0.06148460309168106}, {\"name\": \"spo2_last\", \"direction\": \"risk\", \"magnitude\": 0.04026642407259467}, {\"name\": \"gcs_last\", \"direction\": \"risk\", \"magnitude\": 0.035117962891272}, {\"name\": \"dbp_min\", \"direction\": \"supports\", \"magnitude\": 0.030207761876462156}]}"
    }
  ]
}
```

## Live CLI test — two contrasting patients

```bash
databricks serving-endpoints query icu-readiness --profile icu-sandbox --json '{
  "dataframe_records": [
    { <healthy young patient: lactate=0.4, off-vent, GCS=15, age=38> },
    { <critically ill: lactate=6.2, on-vent+vasopressors, GCS=8, age=78> }
  ]
}'
```

**Response**:
```json
{
  "predictions": [
    {
      "prediction": "{\"readiness_score\": 0.4366819805954576, \"factors\": [{\"name\": \"lactate_last\", \"direction\": \"risk\", \"magnitude\": 0.4742568430719996}, {\"name\": \"age\", \"direction\": \"supports\", \"magnitude\": 0.0755231643072127}, {\"name\": \"rr_mean\", \"direction\": \"supports\", \"magnitude\": 0.07442398991668205}, {\"name\": \"on_ventilator\", \"direction\": \"risk\", \"magnitude\": 0.053011180887023994}, {\"name\": \"spo2_last\", \"direction\": \"risk\", \"magnitude\": 0.03936991405488551}]}"
    },
    {
      "prediction": "{\"readiness_score\": 0.5347027780485188, \"factors\": [{\"name\": \"lactate_last\", \"direction\": \"risk\", \"magnitude\": 0.3017705869567269}, {\"name\": \"spo2_last\", \"direction\": \"supports\", \"magnitude\": 0.2302208792532516}, {\"name\": \"rr_min\", \"direction\": \"risk\", \"magnitude\": 0.14217104073672632}, {\"name\": \"sbp_mean\", \"direction\": \"supports\", \"magnitude\": 0.08012394973570648}, {\"name\": \"age\", \"direction\": \"risk\", \"magnitude\": 0.08003980042366206}]}"
    }
  ]
}
```

> ⚠️ **Calibration warning**: the critically ill patient (score=0.53) scores HIGHER than
> the healthy patient (score=0.44). All scores cluster 0.43–0.54 — the class-weight
> compression effect described in the metrics file. The `readiness_score` is a relative
> ranking, not a calibrated probability. See `phase-5a-report.md` for guidance.

## Endpoint infrastructure

- Serving endpoint created and managed by DABs bundle (`resources/model_serving.yml`)
- Serving entity: `icu_step_down.ml.readiness_model`, version `1`
- Traffic: 100% to `readiness_model-1`
- Verified `state.ready == "READY"` and `state.config_update == "NOT_UPDATING"` before querying
- Scale-to-zero enabled; first query after idle period will have cold-start latency (~30s)

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
score = result["readiness_score"]   # float in ~[0.43, 0.97]
factors = result["factors"]          # list of {name, direction, magnitude}
```

**Factor interface** (matches Phase 5B `Factor(name, direction, magnitude)`):
- `name`: feature name from FEATURE_COLS
- `direction`: `"supports"` (SHAP > 0, pushes toward safe step-down) or `"risk"` (SHAP < 0)
- `magnitude`: absolute SHAP value (higher = more influential)
- Returns top-5 by magnitude

## Notes on re-deployment

To update the model version after retraining:
1. Retrain — new version is registered to `icu_step_down.ml.readiness_model`
2. Set alias: `client.set_registered_model_alias(FULL_NAME, "prod", new_version)`
3. Update `resources/model_serving.yml` entity_version and served_model_name
4. Re-run `databricks bundle deploy -t sandbox --profile icu-sandbox`
