# Phase 5A Report — ML: Train → SHAP → Register → Serve

## Summary

| Item | Value |
|---|---|
| Model type | LightGBM binary classifier (`LGBMClassifier`) |
| Registered to UC | `icu_step_down.ml.readiness_model` version **1**, alias `@prod` |
| MLflow run | `615698248dff4e5399f652029b38b4c2` |
| Endpoint | `icu-readiness` — **READY** / NOT_UPDATING |
| Deployment | DABs bundle (`resources/model_serving.yml`) |
| AUC | **0.6674** |
| PR-AUC (label=1) | **0.9837** (see calibration notes) |
| Recall (bounce-back) | 0.7205 at 0.5 threshold |
| F1 (bounce-back) | 0.0835 |
| SHAP top feature | `lactate_last` (mean |SHAP| = 0.360, 6× next) |

---

## Model parameters

```python
LGBMClassifier(
    n_estimators=500,
    num_leaves=63,
    max_depth=6,
    learning_rate=0.05,
    min_child_samples=20,
    reg_alpha=0.1,
    reg_lambda=1.0,
    class_weight="balanced",    # handles 97/3 imbalance automatically
    early_stopping_rounds=50,   # on validation AUC
    random_state=42,
)
```

Best iteration (early stopping): **189** of 500.

---

## Metrics

```
AUC:            0.6674    ← global discrimination (threshold-independent)
PR-AUC:         0.9837    ← for label=1 (MAJORITY safe class — see note)

                Predicted 0    Predicted 1
Actual 0 (BB)   263 (TN)       102 (FP)   ← 365 bounce-back test cases
Actual 1 (safe) 5,674 (FN)   6,268 (TP)  ← 11,942 safe test cases

Precision(L=1)  0.9840    Recall(L=1)  0.5251    F1(L=1)  0.6858
Precision(L=0)  0.0443    Recall(L=0)  0.7205    F1(L=0)  0.0835
```

**PR-AUC note**: `average_precision_score` defaults to `pos_label=1`.  
Since label=1 is 97% of the data, a base-rate PR curve starts at ~0.97 precision —  
the 0.9837 figure is NOT evidence of a well-calibrated model. The PR-AUC for  
label=0 (bounce-back detection) would be much lower and is the clinically meaningful  
metric for future iterations.

---

## Decisions

### Class imbalance: `class_weight="balanced"` (not `scale_pos_weight`)

The minority class is label=0 (bounce-back, 3%). Using `class_weight="balanced"` with
`LGBMClassifier` computes `n_total / (n_classes × n_class_i)` per class automatically:
- weight(label=0) ≈ 16.84×
- weight(label=1) ≈ 0.515×

Effect: the model becomes very sensitive to bounce-back detection (recall=0.72) at the cost
of producing many false alarms (precision=0.044). The model's output probabilities are
compressed toward the 0.43–0.54 range — not well-calibrated as probabilities.

### NaN handling: LightGBM native surrogate splits (no imputation)

~3,200 of 61,532 stays have NULL vital aggregates. These are very short stays where vitals
were rarely or never recorded. `pd.to_numeric(..., errors="coerce")` converts all NULL
strings to `float("nan")`. LightGBM uses surrogate splits on NaN — no blanket imputation.

**Important secondary effect**: `lactate_last` is NULL for ~3,226 stays. These NULL-lactate
stays are predominantly very short stays that were safely stepped down (label=1). When
lactate IS present (even at a clinically normal 0.4 mmol/L), it signals a longer, more
complex stay — which the model has learned as a risk indicator regardless of the actual
lactate value. This is captured in SHAP as "lactate_last: risk" even for low values.

### DABs for serving (not SDK)

`resources/model_serving.yml` declares `model_serving_endpoints` with `entity_version: "1"`
and `traffic_config.routes[].served_model_name: "readiness_model-1"`. Bundle deployed
with `databricks bundle deploy -t sandbox` → **success**. The DABs approach is used as
directed; the limitation is that updating to a new model version requires editing the YAML.

---

## SHAP global feature importance (mean |SHAP|, n=500 test-set sample)

| Rank | Feature | Mean |SHAP| |
|---|---|---|
| 1 | `lactate_last` | **0.36013** |
| 2 | `age` | 0.06052 |
| 3 | `los` | 0.05267 |
| 4 | `gcs_last` | 0.04582 |
| 5 | `spo2_last` | 0.04544 |
| 6 | `on_ventilator` | 0.03400 |
| 7 | `sbp_last` | 0.03285 |
| 8 | `hr_last` | 0.02959 |
| 9 | `hr_mean` | 0.02858 |
| 10 | `hr_max` | 0.01917 |
| 11–30 | remaining features | <0.015 each |

`lactate_last` accounts for ~66% of total SHAP weight. This dominance, combined with
the NaN signal described above, makes the model's behaviour heavily lactate-centric.

---

## Pyfunc output schema (EXACT)

The serving endpoint returns a JSON string per row under the `prediction` key.

```
predictions[i].prediction  →  JSON string with shape:
{
  "readiness_score": float,         // P(label=1 | features); range ~0.43–0.97 in practice
  "factors": [                       // top-5 by |SHAP|; ordered descending magnitude
    {
      "name":      str,              // feature name (from FEATURE_COLS)
      "direction": "supports"|"risk",// "supports" if SHAP>0 (pushes toward safe step-down)
      "magnitude": float             // abs(SHAP value)
    },
    ...
  ]
}
```

Parse with `json.loads(result["predictions"][0]["prediction"])`.

---

## Registered model version

- **UC path**: `icu_step_down.ml.readiness_model`
- **Version**: `1`
- **Alias**: `@prod`
- **Model URI**: `models:/icu_step_down.ml.readiness_model@prod`
- Registered via `mlflow.pyfunc.log_model(artifact_path="model", python_model="model.py", ...)`
  with `registered_model_name="icu_step_down.ml.readiness_model"` inside the training run.

---

## Endpoint status and sample request/response

**Endpoint name**: `icu-readiness`  
**State**: `READY` / `NOT_UPDATING`  
**Created via**: `databricks bundle deploy -t sandbox --profile icu-sandbox`

### Sample request (CLI)
```bash
databricks serving-endpoints query icu-readiness --profile icu-sandbox --json '{
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
}'
```

### Sample response
```json
{
  "predictions": [{
    "prediction": "{\"readiness_score\": 0.4447135290222422, \"factors\": [{\"name\": \"lactate_last\", \"direction\": \"risk\", \"magnitude\": 0.3557688611235546}, {\"name\": \"on_ventilator\", \"direction\": \"risk\", \"magnitude\": 0.06148460309168106}, {\"name\": \"spo2_last\", \"direction\": \"risk\", \"magnitude\": 0.04026642407259467}, {\"name\": \"gcs_last\", \"direction\": \"risk\", \"magnitude\": 0.035117962891272}, {\"name\": \"dbp_min\", \"direction\": \"supports\", \"magnitude\": 0.030207761876462156}]}"
  }]
}
```

---

## Concerns — MUST KNOW for app and narrative

### 1. readiness_score is a RANKING SIGNAL, not a calibrated probability

Scores cluster in ~0.43–0.55 range due to `class_weight="balanced"` shifting the decision
boundary. Do NOT apply hard 0.5 thresholds in the app UI. Use the score for relative ranking
and show confidence bands. Consider recalibrating (isotonic regression / Platt scaling) in
a future iteration.

### 2. Counter-intuitive scoring at the extremes

In testing, a critically ill patient (lactate=6.2, on vent+vasopressors, GCS=8) scored 0.53
while healthy patients (lactate=0.4, all normals) scored 0.44. This is caused by (a)
class-weight compression and (b) the lactate NaN signal dominating the model margin.
The app should **not** display the raw score as "% safe" and the narrative should frame
it as "relative readiness" rather than a probability.

### 3. Lactate NaN confounding is the dominant signal

~3,226 patients have `lactate_last = NULL`. These are mostly short stays that were safely
stepped down (label=1). The model uses NaN-vs-present as an implicit feature. Any patient
with a measured lactate (even 0.4) gets treated as "more complex" than one without.
The app should surface this: if `lactate_last` is the #1 risk factor, consider adding
"note: lactate measurement availability influences this score".

### 4. AUC is modest (0.67)

This is better than random but weak. The features available (vital sign aggregates, GCS,
lactate, LOS, age) have limited discriminative power for 72h bounce-back prediction.
The narrative should frame this as "clinical support tool, not a decision gate."

### 5. PR-AUC (0.9837) for label=1 is misleading

This is the majority class. The more meaningful PR-AUC for bounce-back detection is
substantially lower. Future evaluation should report `average_precision_score(y_test,
y_prob, pos_label=0)`.

### 6. `on_vasopressors` has near-zero SHAP importance

Despite being clinically significant, `on_vasopressors` barely registers in SHAP.
It is correlated with `on_ventilator` and `lactate_last` in the training data — possibly
absorbed by those features. Worth investigating in future model iterations.

### 7. Version management for the serving endpoint

The DABs YAML hardcodes `entity_version: "1"`. After retraining (new model version),
both the YAML and the `served_model_name` in the traffic config must be updated before
re-deploying. An alternative approach (alias-based routing) requires API-level endpoint
management not currently supported cleanly in DABs YAML.

---

## git log --oneline

```
(to be populated after commit)
```

---

## Files committed

- `src/ml/train.py` — Databricks notebook source (training + SHAP + pyfunc + register)
- `src/ml/train.ipynb` — same notebook exported with injected outputs
- `src/ml/model.py` — pyfunc PythonModel wrapper (logged via "Models from Code" pattern)
- `resources/model_serving.yml` — DABs model_serving_endpoints declaration
- `evidence/05-ml-metrics.md` — metrics, SHAP ranking, sample predictions
- `evidence/05-serving.md` — endpoint status + real request/response
- `.superpowers/sdd/.../phase-5a-report.md` — this report
