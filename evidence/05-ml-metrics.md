# Phase 5 — ML Metrics (current: **v7**)

> **v7 is the served model** (`icu_step_down.ml.readiness_model` version 7, endpoint
> `icu-readiness`). The v6 and v2 records below are kept for comparison — they
> explain why the headline AUC went 0.66 → 0.89 → **0.74**, and why 0.74 is the
> honest number.

## What changed from v6 → v7

| Change | Why |
|---|---|
| **Cohort: stays that left the ICU alive** (pipeline excludes `died_in_icu` — death at or before ICU `outtime` + 1h — and `still_in_icu`) | 4,622 of v6's 5,521 "death" labels (83.7%) were deaths **in** the ICU. Their last-24h feature window is the last day of life — easy to separate from survivors, and not a step-down decision. It inflated test AUC from ~0.72 to 0.89 |
| **Shallower, more regularised trees** (`num_leaves` 15, `min_child_samples` 100, `learning_rate` 0.03, early stopping up to 2,000 trees) | Beat the v6 settings by ~0.015 AUC on the honest cohort in offline experiments |
| **95% bootstrap CIs** on AUC and readmission-only AUC (1,000 resamples of TEST) | ~530 not-safe stays in TEST: AUC moves ±0.02, so single-run differences below that are noise |

Offline experiments that led here (same features, split and seed; nothing
registered) are in [`ml-cohort-experiment.md`](ml-cohort-experiment.md).

## v7 training run

| Field | Value |
|---|---|
| MLflow run_id | `fed422ea54b64609bd4546bbd7c5aae8` |
| Job | `icu-readiness-train` (resources/jobs.yml) — notebook `src/ml/train.py`, run 2026-10-16 |
| Training table | `icu_step_down.gold.readiness_training_set` — **56,860** stays that left the ICU alive (live cohort excluded) |
| Label balance | 54,195 safe / 2,665 not safe (**4.7%**) — 1,766 bounce-backs, 899 deaths within 72h of leaving the ICU |
| Split | 3-way stratified 64/16/20, early stopping on VAL, TEST touched once |
| Registered | version **7**, alias `@prod`; serving pinned to `entity_version: "7"` |

## v7 evaluation (held-out TEST, n = 11,372)

| Metric | v7 | 95% CI | Note |
|---|---|---|---|
| **AUC** | **0.735** | 0.714–0.757 | Safe step-down vs readmission or death within 72h of leaving the ICU |
| AUC — v2 feature set, same cohort | 0.693 | — | The 23 v3 features add ~0.04 |
| **AUC — readmission-only** (post-ICU deaths excluded) | **0.643** | 0.614–0.673 | Bounce-back alone is hard; typical structured-data results on MIMIC are ~0.65–0.75 |
| PR-AUC (not safe) | **0.230** | — | vs 4.7% base rate — ~4.9× lift |
| Precision / recall (not safe) @0.5 | 0.116 / 0.554 | — | Threshold is not used by the app: it shows a relative rank |

Confusion matrix at 0.5 (rows = actual, cols = predicted; order 0 = not safe / 1 = safe):

```
                    Predicted 0    Predicted 1
Actual 0 (not safe)    295 (TN)      238 (FP)
Actual 1 (safe)      2,239 (FN)    8,600 (TP)
```

TEST label_reason: safe 10,839 · bounce_back 362 · death 171.

**How to read it:** v7 ranks patients who left the ICU alive by their risk of
a 72h bounce-back or death, at about 5× the base rate in the riskiest tail.
That's useful for prioritising who to review on rounds, and not good enough to
gate a discharge. The pilot plan validates it on the customer's own patients
(retrospectively, then silently on live patients) before clinicians use it.

## v7 SHAP global importance (mean |SHAP|, TEST sample n = 500)

| Rank | Feature | Mean \|SHAP\| |
|---|---|---|
| 1 | `age` | 0.2747 |
| 2 | `bun_last` | 0.2043 |
| 3 | `urine_output_24h` | 0.1356 |
| 4 | `gcs_last` | 0.0934 |
| 5 | `los` | 0.0773 |
| 6 | `hours_admit_to_icu` | 0.0609 |
| 7 | `hr_last` | 0.0605 |
| 8 | `lactate_last` | 0.0598 |
| 9 | `wbc_last` | 0.0583 |
| 10 | `sodium_last` | 0.0561 |

`ventilated_24h` falls from 5th (v6, 0.189) to 26th (0.017). In v6 it mostly
identified patients who died on the ventilator. GCS falls from 1st to 4th for
the same reason. The life-support guardrail still caps any patient ventilated
or on pressors in the last 24h at Borderline, whatever the model says.

---

# Historical record — v6 (superseded: included in-ICU deaths)

> v6's 0.891 AUC is **not** a valid step-down metric: 84% of its "death" labels
> were deaths in the ICU (see v7 above). Kept for the audit trail.

## What changed from v2 → v6

| Change | Why |
|---|---|
| **Label fixed**: not-safe = ICU readmission **or death** within 72h | v2 counted 5,274 deaths as "safe step-down" (they leave the ICU and are never readmitted) — nearly 3× the true negatives |
| **+23 features** (53 total): last-24h creatinine, BUN, WBC, haemoglobin, platelets, bicarbonate, sodium, potassium, glucose; urine output; HR/SBP/RR/SpO₂ variability; charting density; vasopressors / ventilation **active in the last 24h**; prior ICU stays; emergency admission; hours admission→ICU; surgical / cardiac unit; sex | Standard ICU-readmission predictors available in MIMIC-III at decision time |
| **Leakage fix**: `lactate_last` restricted to values charted before the step-down point | v2 used the last lactate of the whole hospital admission, including post-ICU draws |
| **Census out-of-sample**: the 40 live-cohort stays are excluded from training | v2's training set contained the census patients it then scored |
| **Explicit model signature**: all 53 inputs optional `double` | v2/v3 inferred it from 3 rows → columns marked "required"; a census patient with a missing lab would have failed the whole scoring call |
| **Deterministic split**: rows sorted by `icustay_id` before the stratified split | Spark row order varies; v3–v5 on identical data gave AUC 0.887–0.903 — that spread is split variance |

## v6 training run

| Field | Value |
|---|---|
| MLflow run_id | `b20ebd538eb74184b139ea061b292506` |
| Job | `icu-readiness-train` (resources/jobs.yml) — notebook `src/ml/train.py` |
| Training table | `icu_step_down.gold.readiness_training_set` — **61,492** rows (61,532 stays − 40 live cohort) |
| Label balance | 54,195 safe / 7,297 not safe (**11.9%**) — 5,521 deaths, 1,766 bounce-backs, 10 still in ICU |
| Split | 3-way stratified 64/16/20, early stopping on VAL, TEST touched once |
| Registered | version **6**, alias `@prod`; serving pinned to `entity_version: "6"` |

## v6 evaluation (held-out TEST, n = 12,299)

| Metric | v6 | v2 | Note |
|---|---|---|---|
| **AUC** | **0.891** | 0.659 | Headline: safe step-down vs readmission-or-death |
| AUC — v2 features, v6 label | 0.863 | — | Isolates the label fix: most of the gain comes from the correct outcome |
| **AUC — readmission-only** (deaths excluded from TEST) | **0.635** | (0.659 on v2's own label) | Bounce-back alone is still hard — state this plainly |
| PR-AUC (not safe) | **0.776** | 0.062 | vs 11.9% base rate |
| Precision (not safe) @0.5 | 0.630 | 0.043 | |
| Recall (not safe) @0.5 | 0.725 | 0.734 | |
| F1 (not safe) | 0.674 | 0.082 | |

Confusion matrix (rows = actual, cols = predicted; order 0/1):

```
                    Predicted 0    Predicted 1
Actual 0 (not safe)  1,058 (TN)      401 (FP)
Actual 1 (safe)        621 (FN)   10,219 (TP)
```

TEST label_reason: safe 10,840 · death 1,083 · bounce_back 373 · still_in_icu 3.

**How to read it:** v6 is strong at flagging patients at risk of **dying** if stepped
down — clinically the most important miss to avoid. Predicting 72-hour **readmission**
alone remains modest (AUC 0.63–0.65), about where v2 was. Present the index as decision
support, not a discharge gate.

## v6 SHAP global importance (mean |SHAP|, TEST sample n = 500)

| Rank | Feature | Mean \|SHAP\| |
|---|---|---|
| 1 | `gcs_last` | 0.2970 |
| 2 | `urine_output_24h` | 0.2401 |
| 3 | `age` | 0.2241 |
| 4 | `bun_last` | 0.2012 |
| 5 | `ventilated_24h` | 0.1891 |
| 6 | `sbp_last` | 0.1369 |
| 7 | `los` | 0.1069 |
| 8 | `lactate_last` | 0.1062 |
| 9 | `wbc_last` | 0.0934 |
| 10 | `hours_admit_to_icu` | 0.0847 |
| 11 | `sodium_last` | 0.0806 |
| 12 | `bicarbonate_last` | 0.0804 |

GCS, urine output, age and active ventilation now lead; v2's lactate dominance was
partly the post-ICU leakage fixed above.

---

# Historical record — v2 (superseded)

# Phase 5A — ML Metrics, SHAP Importance, Sample Predictions

> **v2 — clean eval**: 3-way stratified split; early stopping on VAL; TEST set untouched
> until final evaluation. `src/ml/model.py` is the single source of truth for the pyfunc.

## Training run (v2)

| Field | Value |
|---|---|
| MLflow run_id | `ec19dbfd8d474fd7a1aca1c387184f36` |
| Model | LightGBM binary classifier (`LGBMClassifier`) |
| Training table | `icu_step_down.gold.readiness_training_set` (61,532 rows) |
| Split | 3-way stratified: 64% train / 16% val / 20% test |
| Early stopping | on VAL set (50 rounds patience) |
| Final metrics | evaluated ONCE on held-out TEST set |
| Registered model | `icu_step_down.ml.readiness_model` version **2**, alias `@prod` |
| pyfunc source | `src/ml/model.py` (logged via workspace path — committed == deployed) |

## Hyperparameters

```
n_estimators      = 500  (best iteration: 189 via early stopping)
num_leaves        = 63
max_depth         = 6
learning_rate     = 0.05
min_child_samples = 20
reg_alpha         = 0.1
reg_lambda        = 1.0
class_weight      = "balanced"    ← handles 97/3 imbalance
random_state      = 42
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

## Evaluation metrics (test set, n=12,307; evaluated ONCE on held-out TEST)

| Metric | Value | Notes |
|---|---|---|
| **AUC** | **0.6593** | Clean held-out estimate; v1 was 0.6674 (eval-set leak inflated it) |
| **PR-AUC (label=1, safe)** | **0.9830** | Majority class (97% base rate) — high by construction; not a quality headline |
| **PR-AUC (label=0, bounce-back)** | **0.0618** | Clinically meaningful; ~2× base rate (2.97%); modest real signal |
| Precision (label=1, safe) | 0.9842 | At 0.5 threshold |
| Recall (label=1, safe) | 0.5059 | At 0.5 threshold |
| F1 (label=1, safe) | 0.6683 | |
| Precision (label=0, bounce-back) | 0.0434 | Very low — many false alarms |
| **Recall (label=0, bounce-back)** | **0.7342** | 73% of actual bounce-backs detected at 0.5 threshold |
| F1 (label=0, bounce-back) | 0.0820 | |

### Confusion matrix (rows = actual, cols = predicted; order 0/1)

```
                Predicted 0    Predicted 1
Actual 0 (BB)     268 (TN)       97 (FP)   ← 365 bounce-back test cases
Actual 1 (safe)  5,901 (FN)   6,041 (TP)   ← 11,942 safe test cases
```

**Interpretation**: at 0.5 threshold, the model catches 73% of bounce-back cases but produces
~22 false alarms per true bounce-back detection. Clinical use: present `readiness_score`
as a risk ranking signal, not a binary gate.

> **PR-AUC note**: PR-AUC(label=1) = 0.9830 reflects the majority class and is high by
> default (97% base rate — random predictor ≈ 0.97). The clinically meaningful metric is
> **PR-AUC(label=0) = 0.0618**, which is modest (~2× base rate) but represents genuine
> signal over a random ranker. Use this figure for model quality comparisons.

## SHAP global feature importance (mean |SHAP|, test-set sample n=500)

| Rank | Feature | Mean |SHAP| | Clinical note |
|---|---|---|---|
| 1 | `lactate_last` | **0.24580** | Dominant feature — see NaN signal concern below |
| 2 | `age` | 0.04620 | Younger patients score higher |
| 3 | `los` | 0.03491 | Shorter ICU stays correlate with readiness |
| 4 | `gcs_last` | 0.02956 | Higher GCS (→15) supports readiness |
| 5 | `spo2_last` | 0.02939 | High SpO₂ supports readiness |
| 6 | `hr_mean` | 0.02059 | |
| 7 | `rr_mean` | 0.01490 | |
| 8 | `hr_last` | 0.01404 | |
| 9 | `sbp_last` | 0.01382 | |
| 10 | `sbp_mean` | 0.01293 | |
| 11 | `on_ventilator` | 0.01259 | |
| 12–30 | remaining features | <0.012 each | |

> **Key insight**: `lactate_last` is dominant (10× next feature in v1; 5× in v2 after
> proper split). Many short-stay safe patients have `lactate_last = NULL`. When lactate
> IS present, even a low value signals a more clinically complex stay. The model encodes
> this NaN vs. measured distinction via LightGBM's surrogate splits. See concerns below.

## Sample pyfunc predictions (v2 endpoint)

The pyfunc model output schema (per row):
```json
{
  "readiness_score": float,        // P(safe step-down | features); range ~0.44–0.97 in practice
  "factors": [
    {
      "name": "feature_name",
      "direction": "supports" | "risk",
      "magnitude": float           // abs(SHAP value); top-5 by magnitude
    }
  ]
}
```

### Sample A — moderate patient (lactate 1.1, off vent, GCS 15, age 62.5)

```json
{
  "readiness_score": 0.4618,
  "factors": [
    {"name": "lactate_last",  "direction": "risk",     "magnitude": 0.2792},
    {"name": "los",           "direction": "supports", "magnitude": 0.0304},
    {"name": "temp_c_min",    "direction": "risk",     "magnitude": 0.0302},
    {"name": "rr_mean",       "direction": "supports", "magnitude": 0.0270},
    {"name": "spo2_last",     "direction": "risk",     "magnitude": 0.0270}
  ]
}
```

### Sample B — healthy young patient (lactate 0.4, off vent, GCS 15, age 38, los 1.0)

```json
{
  "readiness_score": 0.5262,
  "factors": [
    {"name": "lactate_last",  "direction": "risk",     "magnitude": 0.2123},
    {"name": "age",           "direction": "supports", "magnitude": 0.1640},
    {"name": "rr_last",       "direction": "supports", "magnitude": 0.0662},
    {"name": "on_ventilator", "direction": "risk",     "magnitude": 0.0298},
    {"name": "spo2_last",     "direction": "risk",     "magnitude": 0.0244}
  ]
}
```

### Sample C — critically ill (lactate 6.2, on vent+vasopressors, GCS 8, age 78, los 7.5)

```json
{
  "readiness_score": 0.4436,
  "factors": [
    {"name": "lactate_last", "direction": "risk",     "magnitude": 0.2262},
    {"name": "rr_min",       "direction": "risk",     "magnitude": 0.1112},
    {"name": "spo2_last",    "direction": "supports", "magnitude": 0.1058},
    {"name": "hr_last",      "direction": "risk",     "magnitude": 0.0723},
    {"name": "los",          "direction": "risk",     "magnitude": 0.0335}
  ]
}
```

> v2 clinical ordering is now correct: healthy (0.526) > moderate (0.462) > critically ill (0.444).
> v1 had this inverted (critically ill scored higher) due to the eval-set leak changing
> the learned boundary. Scores still cluster near 0.44–0.53 due to `class_weight="balanced"`
> compressing the probability range — see the report concerns section.
