# Offline cohort experiment (2026-10-16): why v6's 0.89 AUC was inflated

Read-only experiment run before model v7. It pulled every ICU stay from
`gold.patient_features` with v6's outcome labels plus candidate features, then retrained LightGBM
locally with v6's split and seed. **Nothing was registered or deployed.**

Scripts: `scripts/ml_experiments/pull_cohort_data.py` (pull to a gitignored
`data/`) and `scripts/ml_experiments/cohort_experiment.py`. The pull builds
v6's outcome labels from `gold.patient_features`, so run A stays reproducible
now that the pipeline drops in-ICU deaths from the training set. Each run's
CI uses its own seeded RNG, so runs can be re-run individually.

## Finding: 84% of the "death" labels were deaths in the ICU

| Where the 5,521 v6 "death" stays died | Stays | Share | Median hours after ICU `outtime` |
|---|---|---|---|
| **In the ICU** (`deathtime` ≤ `outtime` + 1h) | **4,622** | **83.7%** | −2.7 |
| In hospital, within 72h of leaving the ICU | 696 | 12.6% | 23.8 |
| After hospital discharge, within 72h (`dod` date only) | 203 | 3.7% | 24.6 |

The features cover the last 24h before `outtime`. For an in-ICU death, that's the
last day of life: low GCS, no urine, ventilated. Separating those patients from
survivors is easy, and none of them was a step-down decision.

## Results (TEST set, 95% bootstrap CI, 1,000 resamples; re-run 2026-10-16)

| Experiment | AUC | Readmission-only AUC | PR-AUC (base rate) |
|---|---|---|---|
| **A** v6 as-is (all stays, 53 features) | 0.892 [0.882–0.903] | 0.620 [0.590–0.653] | 0.777 (0.119) |
| **B** stays that left the ICU alive, 53 features | **0.716** [0.693–0.738] | 0.631 [0.603–0.657] | 0.188 (0.047) |
| B, patient-grouped split | 0.722 [0.699–0.745] | 0.626 [0.599–0.652] | 0.217 (0.049) |
| **C** B + 22 features (6h trend and 24h slope for 6 vitals, discharge hour/night/weekend, hours since last ventilator chart) | 0.718 [0.696–0.740] | 0.635 [0.605–0.660] | 0.192 (0.047) |
| C, patient-grouped split | 0.719 [0.696–0.743] | 0.626 [0.597–0.654] | 0.216 (0.049) |
| **D** C trained on bounce-back vs safe only | 0.609 [0.586–0.632] | 0.601 [0.572–0.629] | 0.072 (0.047) |
| D, tuned (`num_leaves` 15, `min_child_samples` 100) | 0.666 [0.644–0.688] | 0.654 [0.625–0.680] | 0.093 (0.047) |
| D, tuned, 53 features only | 0.662 [0.639–0.684] | 0.648 [0.619–0.675] | 0.092 (0.047) |
| **E** C tuned (`num_leaves` 15, `min_child_samples` 100, lr 0.03) | **0.732** [0.709–0.755] | **0.648** [0.619–0.672] | 0.202 (0.047) |
| E variant (`num_leaves` 31, `min_child_samples` 50) | 0.725 [0.702–0.749] | 0.641 [0.613–0.667] | 0.195 (0.047) |
| E variant (`num_leaves` 7, `min_child_samples` 200, lr 0.02) | 0.732 [0.710–0.755] | 0.649 [0.621–0.674] | 0.197 (0.047) |

## Conclusions → model v7

- **Excluding in-ICU deaths drops AUC from 0.89 to about 0.72.** The pipeline now
  does this (`label_reason = 'died_in_icu'` is excluded from
  `gold.readiness_training_set`).
- **Splitting by patient doesn't change the result**, so the same patient
  appearing in train and test isn't leaking information.
- **The 22 candidate features add nothing measurable** (+0.002), so they are not
  in v7.
- **Shallower, regularised trees add about 0.015**, and two different settings
  agree. v7 uses `num_leaves` 15 and `min_child_samples` 100.
- **A bounce-back-only target doesn't help overall.** Readmission-only AUC moves
  within noise.
- **Readmission-only AUC of about 0.65 is near the ceiling for 24h structured
  features.** Notes, comorbidities from prior admissions, or discharge
  medications would be the next levers.

v7 retrained in the workspace on the same cohort and settings: **AUC 0.735
[0.714–0.757], readmission-only 0.643 [0.614–0.673]**. See
[`05-ml-metrics.md`](05-ml-metrics.md).

> A first run of D reported readmission-only AUC 0.79. That came from a bug in
> the experiment: its test rows overlapped its training rows. The fixed numbers
> are above.
