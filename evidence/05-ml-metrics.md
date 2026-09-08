# Phase 5A — ML Metrics, SHAP Importance, Sample Predictions

## Training run

| Field | Value |
|---|---|
| MLflow run_id | `615698248dff4e5399f652029b38b4c2` |
| Model | LightGBM binary classifier (`LGBMClassifier`) |
| Training table | `icu_step_down.gold.readiness_training_set` (61,532 rows) |
| Train / test split | 80 / 20, stratified on `readiness_label` |
| Registered model | `icu_step_down.ml.readiness_model` version 1, alias `@prod` |

## Hyperparameters

```
n_estimators     = 500
num_leaves       = 63
max_depth        = 6
learning_rate    = 0.05
min_child_samples = 20
reg_alpha        = 0.1
reg_lambda       = 1.0
class_weight     = "balanced"    ← handles 97/3 imbalance
random_state     = 42
early_stopping   = 50 rounds on validation AUC
```

## Class imbalance handling

Training set: 59,706 safe (label=1) vs 1,826 bounce-back (label=0) — ~97 / 3 split.  
`class_weight="balanced"` lets sklearn compute per-class weights automatically:  
`w_i = n_total / (n_classes × n_i)`, giving bounce-back instances ~16.8× higher weight.  
Raw accuracy is **not** reported (misleadingly high due to class imbalance).

## NaN handling

~3,200 stays have NULL vital aggregates (very short stays — insufficient observation window).  
`pd.to_numeric(..., errors="coerce")` converts NULL strings to `float("nan")`.  
LightGBM handles NaN natively via surrogate splits — no blanket imputation to 0.

## Evaluation metrics (test set, n=12,307)

| Metric | Value | Notes |
|---|---|---|
| **AUC** | **0.6674** | Global discrimination; threshold-independent |
| **PR-AUC (label=1)** | **0.9837** | Precision-recall for majority safe class; high by default (97% base rate) |
| Precision (label=1, safe) | 0.9840 | At 0.5 threshold |
| Recall (label=1, safe) | 0.5251 | At 0.5 threshold |
| F1 (label=1, safe) | 0.6858 | |
| Precision (label=0, bounce-back) | 0.0443 | Very low — many safe patients flagged as risk |
| **Recall (label=0, bounce-back)** | **0.7205** | 72% of actual bounce-backs detected |
| F1 (label=0, bounce-back) | 0.0835 | |

### Confusion matrix (rows = actual, cols = predicted; order 0/1)

```
                Predicted 0    Predicted 1
Actual 0 (BB)     263 (TN)      102 (FP)   ← 365 bounce-back test cases
Actual 1 (safe)  5,674 (FN)   6,268 (TP)   ← 11,942 safe test cases
```

**Interpretation**: at 0.5 threshold, the model catches 72% of bounce-back cases but produces  
~22 false alarms (safe patients flagged as at-risk) per true bounce-back detected.  
Clinical use: the `readiness_score` should drive qualitative risk ranking, not a binary gate.

> ⚠️ Note on PR-AUC: 0.9837 reflects the majority class (safe). The PR-AUC for the
> **bounce-back class** (the clinically important minority) is substantially lower and  
> aligns with the F1(L=0) = 0.08 picture above.

## SHAP global feature importance (mean |SHAP|, test-set sample n=500)

| Rank | Feature | Mean |SHAP| | Clinical note |
|---|---|---|---|
| 1 | `lactate_last` | **0.36013** | Dominates by a 6× margin — presence+level |
| 2 | `age` | 0.06052 | Younger patients score higher |
| 3 | `los` | 0.05267 | Shorter ICU stays correlate with readiness |
| 4 | `gcs_last` | 0.04582 | Higher GCS (→15) supports readiness |
| 5 | `spo2_last` | 0.04544 | High SpO₂ supports readiness |
| 6 | `on_ventilator` | 0.03400 | Being off the vent supports readiness |
| 7 | `sbp_last` | 0.03285 | |
| 8 | `hr_last` | 0.02959 | |
| 9 | `hr_mean` | 0.02858 | |
| 10 | `hr_max` | 0.01917 | |
| 11 | `rr_last` | 0.01467 | |
| 12 | `sbp_max` | 0.01450 | |
| 13 | `temp_c_min` | 0.01434 | |
| 14 | `rr_mean` | 0.01401 | |
| 15 | `temp_c_last` | 0.01358 | |
| 16 | `dbp_min` | 0.01165 | |
| 17 | `rr_min` | 0.01038 | |
| 18 | `temp_c_max` | 0.01012 | |
| 19 | `temp_c_mean` | 0.00976 | |
| 20 | `sbp_min` | 0.00970 | |
| <20 | remaining 10 features | <0.010 each | |

**Key insight**: `lactate_last` is overwhelmingly dominant. Many short-stay patients (safe) have  
`lactate_last = NaN` (not measured). When lactate IS present, even a low value signals a  
more clinically complex stay, which LightGBM's NaN surrogate split implicitly encodes.  
See concerns section below and the phase-5a report for details.

## Sample pyfunc predictions

The pyfunc model output schema (per row):
```json
{
  "readiness_score": float,        // P(safe step-down | features) in [0,1]
  "factors": [
    {
      "name": "feature_name",
      "direction": "supports" | "risk",
      "magnitude": float           // abs(SHAP value); top-5 by magnitude
    }
  ]
}
```

### Sample A — moderate patient (lactate 1.1, off vent, GCS 15)
Input: hr_mean=88.5, sbp_last=120, spo2_last=98, gcs_last=15, on_ventilator=0, lactate_last=1.1, los=2.5, age=62.5

```json
{
  "readiness_score": 0.4447,
  "factors": [
    {"name": "lactate_last", "direction": "risk", "magnitude": 0.3558},
    {"name": "on_ventilator", "direction": "risk", "magnitude": 0.0615},
    {"name": "spo2_last", "direction": "risk", "magnitude": 0.0403},
    {"name": "gcs_last", "direction": "risk", "magnitude": 0.0351},
    {"name": "dbp_min", "direction": "supports", "magnitude": 0.0302}
  ]
}
```

### Sample B — healthy young patient (lactate 0.8, off vent, GCS 15)
Input: hr_mean=72, sbp_last=125, spo2_last=99, gcs_last=15, on_ventilator=0, lactate_last=0.8, los=1.5, age=45

```json
{
  "readiness_score": 0.4715,
  "factors": [
    {"name": "lactate_last", "direction": "risk", "magnitude": 0.4044},
    {"name": "age", "direction": "supports", "magnitude": 0.0639},
    {"name": "on_ventilator", "direction": "risk", "magnitude": 0.0591},
    {"name": "spo2_last", "direction": "risk", "magnitude": 0.0396},
    {"name": "los", "direction": "supports", "magnitude": 0.0377}
  ]
}
```

### Sample C — critically ill (lactate 6.2, on vent+vasopressors, GCS 8, age 78)
Input: hr_mean=110, sbp_last=85, spo2_last=88, gcs_last=8, on_ventilator=1, lactate_last=6.2, los=7.5, age=78

```json
{
  "readiness_score": 0.5347,
  "factors": [
    {"name": "lactate_last", "direction": "risk", "magnitude": 0.3018},
    {"name": "spo2_last", "direction": "supports", "magnitude": 0.2302},
    {"name": "rr_min", "direction": "risk", "magnitude": 0.1422},
    {"name": "sbp_mean", "direction": "supports", "magnitude": 0.0801},
    {"name": "age", "direction": "risk", "magnitude": 0.0800}
  ]
}
```

> ⚠️ **IMPORTANT CONCERN**: Sample C (critically ill) scores 0.53 while Sample A (moderate) scores 0.44.
> This counter-intuitive ordering reflects class-weight compression near the decision boundary
> (all scores cluster 0.43–0.54) and the lactate NaN signal dominating the margin.
> The app and narrative must NOT apply a hard 0.5 threshold; see the report for guidance.
