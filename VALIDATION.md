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
| **Lakeflow pipeline** | `icu-step-down-readiness-medallion` · `f216d643-ef34-425f-a09a-f1b797b55395` | Deployed; CONTINUOUS mode (serverless, 24/7 unless paused) | [`evidence/pipeline-run.log`](evidence/pipeline-run.log) (event log + row counts), [`evidence/bundle-deploy.log`](evidence/bundle-deploy.log), [`evidence/streaming-run.txt`](evidence/streaming-run.txt) |
| **UC gold tables** | `icu_step_down.gold.{census, patient_features, readiness_training_set, census_vitals, pii_audit, census_serving, patient_features_serving}` | 40 / 61,532 / 61,532 / 40 (MV) / audit / 40 pseudonym / 61,532 pseudonym rows | [`evidence/gold-queries.txt`](evidence/gold-queries.txt), [`evidence/pii-obfuscation.txt`](evidence/pii-obfuscation.txt) |
| **Landing stage (replay)** | `icu_step_down.landing.{live_cohort, chart_events_feed, replay_clock}` | 40 frozen cohort / event stream / timing log | [`evidence/streaming-run.txt`](evidence/streaming-run.txt) |
| **UC governance** | grants + PII tags; UC column masks on `subject_id` / `hadm_id`; `care_unit` secure views `census_governed`, `patient_features_governed` | Applied; fail-closed verified live | [`src/governance/pii_masking.sql`](src/governance/pii_masking.sql), [`src/governance/governance.sql`](src/governance/governance.sql), [`evidence/unit-access-verification.txt`](evidence/unit-access-verification.txt), [`evidence/pii-obfuscation.txt`](evidence/pii-obfuscation.txt) |
| **PII masking functions** | `icu_step_down.gold.pseudonymize_id()`, `icu_step_down.gold.mask_patient_id()` | Deployed (deterministic SHA-256 pseudonym P-xxxxxxxx) | [`src/governance/pii_masking.sql`](src/governance/pii_masking.sql), [`evidence/pii-obfuscation.txt`](evidence/pii-obfuscation.txt) |
| **ML model** | `icu_step_down.ml.readiness_model` **v7** (LightGBM + SHAP; 53 features; left-ICU-alive cohort; test AUC 0.735 [0.714–0.757] / readmission-only 0.643 / not-safe PR-AUC 0.230) | Registered; served via `icu-readiness` endpoint | [`src/ml/train.py`](src/ml/train.py), [`evidence/05-ml-metrics.md`](evidence/05-ml-metrics.md) |
| **Model training job** | `icu-readiness-train` | Deployed (DAB bundle job; serverless; run via `databricks bundle run`) | [`resources/jobs.yml`](resources/jobs.yml), [`src/ml/train.py`](src/ml/train.py) |
| **Model serving endpoint** | `icu-readiness` | Deployed ([live URL in log](evidence/bundle-deploy.log)) | [`evidence/serving-prediction.json`](evidence/serving-prediction.json) (real response), [`evidence/serving-prediction.txt`](evidence/serving-prediction.txt) |
| **Genie space** | "ICU Step-Down Readiness" (see `space_config.md` for space ID) · 3 governed tables | Configured | [`evidence/genie-conversation.md`](evidence/genie-conversation.md) (live Q&A), [`src/genie/space_config.md`](src/genie/space_config.md) |
| **Lakebase** | project `icu-step-down` / branch `production` · UC catalog `icu_step_down_lakebase` | Synced tables **ONLINE**: `census_serving`, `patient_features_serving` (pseudonymized), `census_vitals`, `readiness_drift` | [`evidence/lakebase-query.txt`](evidence/lakebase-query.txt), [`evidence/pii-obfuscation.txt`](evidence/pii-obfuscation.txt) |
| **Streaming replay job** | `icu-live-vitals-replay` (schedule **paused** by default) | Deployed; every 5 min releases 1h of frozen-cohort real chart events | [`resources/jobs.yml`](resources/jobs.yml), [`src/streaming/replay_vitals.py`](src/streaming/replay_vitals.py), [`evidence/streaming-run.txt`](evidence/streaming-run.txt) |
| **Databricks App** | `icu-step-down` · https://icu-step-down-7474645901826067.aws.databricksapps.com | **RUNNING** | [`evidence/app-deploy.log`](evidence/app-deploy.log), [`evidence/07-app-deploy.md`](evidence/07-app-deploy.md) |
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

`evidence/test-run.log` — **199 backend + 38 frontend + 69 pipeline/ML unit + 27 live integration = 333 passing** (note: 1 integration test skipped pending replay completion; monitoring/genai/streaming integrated into root test suite).

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
