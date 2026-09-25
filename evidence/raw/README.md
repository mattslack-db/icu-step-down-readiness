# Raw execution evidence (live-captured CLI/API output)

These files are **verbatim output captured from live runs** against the Databricks
sandbox `fe-sandbox-icu-step-down-readiness.cloud.databricks.com` (CLI profile
`icu-sandbox`) on **2026-09-25**. They are not hand-written summaries — each file is
the raw stdout/JSON returned by the Databricks CLI / REST API, so the build can be
confirmed to have actually executed end to end.

> The environment was rebuilt on 2026-09-25 after the original sandbox's 30-day TTL
> expired (workspace destroyed 2026-09-21). The regional Unity Catalog metastore and
> the registered model survived; the Lakeflow pipeline, serving endpoint, Lakebase
> instance, and Genie space were redeployed and re-run to regenerate this evidence.

| File | Stage | What it proves |
|------|-------|----------------|
| [`gold-queries.txt`](gold-queries.txt) | Unity Catalog (gold) | Live SQL results against the governed `icu_step_down.gold.*` tables — row counts, label balance, vasopressor/ventilator prevalence, census cohort |
| [`serving-prediction.txt`](serving-prediction.txt) | ML serving | Real request → response from the Mosaic AI endpoint `icu-readiness` (model `icu_step_down.ml.readiness_model` v2): `readiness_score` + SHAP factors for two patients |
| [`genie-qa.txt`](genie-qa.txt) | Genie | Five natural-language questions via the Genie Conversation API → generated SQL → result rows, from space `01f1b92aeef914e383e43c1452d294cf` |
| [`pipeline-run.txt`](pipeline-run.txt) | Lakeflow | Pipeline update event log + per-layer bronze→silver→gold row counts from a full run of `icu-step-down-readiness-medallion` |
| [`lakebase-query.txt`](lakebase-query.txt) | Lakebase | Synced tables ONLINE (`census`, `patient_features`, `census_vitals`) + row counts read from the Lakebase Postgres via the `mimic_iii` catalog |
| [`app-deploy.txt`](app-deploy.txt) | Databricks App | App `icu-step-down` RUNNING + uvicorn startup logs (Lakebase connection succeeded) |

## How to reproduce

```bash
# gold query results
databricks experimental aitools tools query "SELECT COUNT(*) FROM icu_step_down.gold.census" --profile icu-sandbox

# served prediction (payload in scripts/, 30 features per patient)
databricks serving-endpoints query icu-readiness --json @request.json --profile icu-sandbox

# genie Q&A
SPACE_ID=<space> bash scripts/capture_genie_qa.sh

# pipeline run
databricks pipelines start-update <pipeline_id> --profile icu-sandbox
```
