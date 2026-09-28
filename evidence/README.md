# evidence/ — all run outputs, logs, notebooks, and diagrams

Everything proving the build ran, in one folder (previously split across
`logs/` and `evidence/raw/`, now consolidated here). All text/CSV/JSON/log/md
so it is readable by reviewers; the full asset manifest is in
[`../VALIDATION.md`](../VALIDATION.md).

## Execution logs & results (live-captured)

| File | What it proves |
|------|----------------|
| [`pipeline-run.log`](pipeline-run.log) / [`pipeline-run.txt`](pipeline-run.txt) | Lakeflow pipeline run — every flow COMPLETED + bronze→gold row counts |
| [`query-results.csv`](query-results.csv) / [`gold-queries.txt`](gold-queries.txt) | Query results against the governed `icu_step_down.gold.*` tables |
| [`serving-prediction.json`](serving-prediction.json) / [`serving-prediction.txt`](serving-prediction.txt) | Real `icu-readiness` endpoint response (score + SHAP factors) |
| [`genie-conversation.md`](genie-conversation.md) / [`genie-qa.txt`](genie-qa.txt) | Genie NL question → generated SQL → result rows |
| [`app-deploy.log`](app-deploy.log) / [`app-deploy.txt`](app-deploy.txt) | Databricks App RUNNING + uvicorn startup logs |
| [`bundle-deploy.log`](bundle-deploy.log) | DABs `bundle deploy` + `validate` (OK) + `summary` (deployed resource URLs) |
| [`drift-metrics.csv`](drift-metrics.csv) / [`drift-run.txt`](drift-run.txt) / [`drift-baseline.txt`](drift-baseline.txt) | Live model-drift job (PSI 2.15 / KS 0.22) + baseline |
| [`lakebase-query.txt`](lakebase-query.txt) | Lakebase synced tables ONLINE + Postgres row counts |
| [`gold-derived-signals.txt`](gold-derived-signals.txt) | `recent_extubation` / `active_bleeding` prevalence |
| [`care-unit-distribution.txt`](care-unit-distribution.txt) | Synthetic `care_unit` (MICU/SICU/CCU) distribution |
| [`unit-access-verification.txt`](unit-access-verification.txt) | Live read-only proof of the unit-access mechanism |
| [`test-run.log`](test-run.log) | Test suites passing (188 backend + 36 frontend + 18 monitoring/genai) |

## Notebooks (committed with cell outputs)

| File | Notes |
|------|-------|
| [`train.ipynb`](train.ipynb) | Copy of `../src/ml/train.ipynb` — model training (LightGBM + SHAP), 6/6 code cells with outputs |
| [`execution-evidence.ipynb`](execution-evidence.ipynb) | End-to-end run reproduction, 6/6 code cells with outputs |

## Diagrams, phase notes, and media

- Architecture: [`architecture.md`](architecture.md) (Mermaid text) + [`architecture.png`](architecture.png)
- Phase-by-phase build notes: `00-provisioning.md` … `08-tests.md` (+ `00-bundle-validate.txt`)
- App screenshots: `screenshot-census.png`, `screenshot-analytics.png`, `screenshot-patient-detail.png` (binary — attach separately)
- Demo recording placeholder: [`RECORDING.md`](RECORDING.md)
