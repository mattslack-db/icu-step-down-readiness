# VALIDATION.md — asset manifest & proof index

One place that lists **every asset in this build** — each deployed Databricks
resource and each repo artifact — with its identifier, status, and the
**committed, readable proof** it ran. Companion to [`README.md`](README.md)
(what/how), [`BUILD.md`](BUILD.md) (how built + AI), [`EVIDENCE.md`](EVIDENCE.md)
and [`evidence/`](evidence/) (raw run output), and [`DATA-JOURNEY.md`](DATA-JOURNEY.md)
(transformation logic).

> Data is public, de-identified **MIMIC-III** (Delta Share). No secrets or real
> customer data (pre-commit secret scan enforced); `care_unit` is synthetic.

---

## 1. Deployed Databricks assets (target `sandbox`, workspace `fe-sandbox-icu-step-down-readiness`)

| Asset | Identifier | Status | Readable proof |
|-------|-----------|--------|----------------|
| **Lakeflow pipeline** | `icu-step-down-readiness-medallion` · `f216d643-ef34-425f-a09a-f1b797b55395` | Deployed; last update **COMPLETED** | [`evidence/pipeline-run.log`](evidence/pipeline-run.log) (event log + row counts), [`evidence/bundle-deploy.log`](evidence/bundle-deploy.log) |
| **UC gold tables** | `icu_step_down.gold.{census, patient_features, readiness_training_set}` | 40 / 61,532 / 61,532 rows | [`evidence/query-results.csv`](evidence/query-results.csv), [`evidence/gold-queries.txt`](evidence/gold-queries.txt) |
| **UC governance** | grants + PII tags; `care_unit` secure views `census_governed`, `patient_features_governed` | Applied; fail-closed verified live | [`src/governance/`](src/governance/), [`evidence/unit-access-verification.txt`](evidence/unit-access-verification.txt) |
| **ML model** | `icu_step_down.ml.readiness_model` **v2** (LightGBM + SHAP) | Registered | [`src/ml/train.ipynb`](src/ml/train.ipynb) (notebook **with outputs**), [`evidence/05-ml-metrics.md`](evidence/05-ml-metrics.md) |
| **Model serving endpoint** | `icu-readiness` | Deployed ([live URL in log](evidence/bundle-deploy.log)) | [`evidence/serving-prediction.json`](evidence/serving-prediction.json) (real response), [`evidence/serving-prediction.txt`](evidence/serving-prediction.txt) |
| **Genie space** | "ICU Step-Down Readiness" (see `space_config.md` for space ID) · 3 governed tables | Configured | [`evidence/genie-conversation.md`](evidence/genie-conversation.md) (live Q&A), [`src/genie/space_config.md`](src/genie/space_config.md) |
| **Lakebase** | project `icu-step-down` / branch `production` | Synced tables **ONLINE**: `census`, `patient_features`, `census_vitals`, `readiness_drift` | [`evidence/lakebase-query.txt`](evidence/lakebase-query.txt) |
| **Databricks App** | `icu-step-down` · https://icu-step-down-7474645692590282.aws.databricksapps.com | **RUNNING** | [`evidence/app-deploy.log`](evidence/app-deploy.log), [`evidence/07-app-deploy.md`](evidence/07-app-deploy.md) |
| **Drift monitoring** | `icu_step_down.gold.readiness_drift` → synced to Lakebase | Ran: **PSI 2.15 / KS 0.22** (verdict drift, n=40) | [`evidence/drift-metrics.csv`](evidence/drift-metrics.csv), [`evidence/drift-run.txt`](evidence/drift-run.txt) |
| **DABs bundle** | `icu_step_down`, target `sandbox` | **Validation OK** | [`evidence/bundle-deploy.log`](evidence/bundle-deploy.log), [`evidence/00-bundle-validate.txt`](evidence/00-bundle-validate.txt) |

**Honest note:** in `bundle summary` the drift **job** resource
(`icu-readiness-drift-check`) shows `(not deployed)` — the drift check was run
directly (a one-off job run), and its results are committed above; the pipeline
and serving-endpoint resources are bundle-deployed with live URLs.

## 2. Notebooks (committed with cell outputs)

| Notebook | Cells with outputs | Purpose |
|----------|--------------------|---------|
| [`src/ml/train.ipynb`](src/ml/train.ipynb) | 6 / 6 code cells | Model training (LightGBM + SHAP), metrics, registration |
| [`evidence/execution-evidence.ipynb`](evidence/execution-evidence.ipynb) | 6 / 6 code cells | End-to-end run reproduction (pipeline counts, prediction, Genie, drift, app) |
| `scripts/create synced tables for Lakebase mimic.ipynb` | partial | Lakebase sync utility (setup notebook) |

## 3. Documentation & presentation

| Artifact | Location |
|----------|----------|
| Project README (what + how to run) | [`README.md`](README.md) |
| Build/AI write-up (workflow, tools, prompts, decisions) | [`BUILD.md`](BUILD.md) |
| Data-journey (medallion SQL + Genie config, readable) | [`DATA-JOURNEY.md`](DATA-JOURNEY.md) |
| Execution-evidence narrative | [`EVIDENCE.md`](EVIDENCE.md) |
| Architecture diagram | [`evidence/architecture.md`](evidence/architecture.md) (Mermaid text) + [`evidence/architecture.png`](evidence/architecture.png) |
| Phase-by-phase evidence notes | [`evidence/`](evidence/) `00`–`08` |
| Presentation (PDF) | [`deck/icu-step-down-readiness.pdf`](deck/icu-step-down-readiness.pdf) — **attach separately** (binary; HTML alone not accepted) |
| App screenshots | `evidence/screenshot-{census,analytics,patient-detail}.png` — **attach separately** (binary) |
| Demo recording | [`evidence/RECORDING.md`](evidence/RECORDING.md) — **submitter adds link** |

## 4. Tests

`evidence/test-run.log` — **188 backend + 36 frontend + 18 monitoring/genai = 242
passing** locally, + 17 live-integration tests (skip without the
`databricks-sql-connector`; run green in the sandbox).

## 5. Submission-guideline compliance

| Requirement | Status |
|-------------|--------|
| README (what + how to run) | ✅ |
| BUILD.md (workflow, AI tools/prompts, decisions) | ✅ |
| evidence/ — run outputs, architecture diagram | ✅ |
| Notebook(s) committed with outputs | ✅ (`train.ipynb`, `execution-evidence.ipynb`) |
| Deploy logs (pipeline/serving/app + bundle) | ✅ (`evidence/bundle-deploy.log`, `evidence/pipeline-run.log`, `evidence/app-deploy.log`) |
| No secrets / real customer data | ✅ (public MIMIC-III, synthetic `care_unit`, secret scan) |
| Presentation as PDF/Slides | ✅ PDF exists — **attach separately** |
| Screenshots showing app/results | ⚠️ present — **attach separately** (binaries excluded from repo scan) |
| Demo recording link | ⚠️ **submitter adds** in `evidence/RECORDING.md` |
