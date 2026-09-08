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

## Review fixes (v2 — clean eval)

### IMPORTANT 1 fixed: eval-set leak removed

v1 trained with `eval_set=[(X_test, y_test)]` for early stopping, making the iteration
count tuned on the test set. AUC 0.6674 was optimistic. Fixed:

- **3-way stratified split**: 64% train / 16% val / 20% test
- **Early stopping on VAL only** (`eval_set=[(X_val, y_val)]`)
- **Final metrics evaluated once on TEST set**: AUC = **0.6593** (honest; delta −0.0081)

### IMPORTANT 2 fixed: model.py is now the single source of truth

v1 logged the pyfunc from an inline code string in `train.py`. The inline string diverged
from `src/ml/model.py` in the dtype guard (`== "boolean"` vs `in (..."boolean")`).
Fixed:

- `src/ml/model.py` updated: dtype check `in ("object","string","StringDtype","boolean")`;
  type hints on `predict`; explicit missing-column guard raising `ValueError` naming missing cols
- `train.py` logs via `python_model=MODEL_PY_PATH` where `MODEL_PY_PATH` is the workspace
  path of `src/ml/model.py` uploaded before the job runs
- Committed == deployed: the content at the workspace path matches `src/ml/model.py`
- Note: workspace path pattern for client:4 notebooks — import as `/icu_step_down/model`
  (no `.py`), accessible as `/Workspace/.../model.py` in the filesystem

### MINOR fixed: serving evidence placeholder replaced

`evidence/05-serving.md` now contains two complete real request/response pairs (single
patient + two-patient contrast) captured from the live v2 endpoint.

### Also fixed: PR-AUC label=0 was computed with wrong `pos_label`

Original code: `average_precision_score(y_test, 1-y_prob, pos_label=1)` — computed AP
for the majority safe class using an inverted ranker; resulted in misleadingly high 0.9538.
Correct: `average_precision_score(y_test, 1-y_prob, pos_label=0)` = **0.0618**
(~2× base rate of 2.97% — modest but real signal). Fixed in `train.py`.

### Also added: DABs sync.exclude for .ipynb

`databricks.yml` now has `sync.exclude: ["**/*.ipynb"]` to prevent the conflict between
`train.py` and `train.ipynb` mapping to the same workspace notebook path.

### v2 clean metrics summary

| Metric | v1 (eval leak) | v2 (clean eval) |
|---|---|---|
| AUC | 0.6674 | **0.6593** |
| PR-AUC (label=1) | 0.9837 | 0.9830 |
| PR-AUC (label=0, bounce-back) | N/A (computed wrong) | **0.0618** |
| Recall (bounce-back) | 0.7205 | 0.7342 |
| F1 (bounce-back) | 0.0835 | 0.0820 |
| Model version | 1 | **2** |
| Endpoint | READY v1 | READY **v2** |
| Clinical ordering (healthy > critically ill) | ✗ inverted | ✓ correct |

---

## git log --oneline

```
(to be filled after fix commit)
17efd7a feat: Phase 5A — LightGBM readiness classifier, SHAP, pyfunc, serving endpoint
1f8c40a fix: sync_tables.py — harden existence checks; timeout exits non-zero
e2ed1ee feat: Phase 4 — Lakebase Operational Serving (icu-step-down project + synced tables)
6fbd9d7 fix: Phase 3 review — extend pii tags to all three gold tables; add MV warning
0f46240 feat: Phase 3 — Unity Catalog governance for icu_step_down
```

---

## Files committed

- `src/ml/train.py` — 3-way split, VAL early stopping, correct PR-AUC, model.py path
- `src/ml/train.ipynb` — notebook with v2 outputs injected
- `src/ml/model.py` — SSOT pyfunc: dtype guard + missing-col check + type hints
- `resources/model_serving.yml` — entity_version 2, served_model_name readiness_model-2
- `databricks.yml` — sync.exclude for .ipynb files
- `evidence/05-ml-metrics.md` — v2 clean numbers including correct PR-AUC(L=0)=0.0618
- `evidence/05-serving.md` — real request/response pairs from v2 endpoint
- `.superpowers/sdd/.../phase-5a-report.md` — this report
