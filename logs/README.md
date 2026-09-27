# logs/ — execution evidence (live-captured run output)

Top-level, multi-format copies of the build's **actual run output**, captured
verbatim from live executions against the Databricks sandbox
`fe-sandbox-icu-step-down-readiness` (CLI profile `icu-sandbox`). This is real
output, not narrative — surfaced here at the repo root so it is trivially
discoverable.

| File | Format | What it proves |
|------|--------|----------------|
| [`pipeline-run.log`](pipeline-run.log) | log | Lakeflow pipeline run event log (every flow COMPLETED) + bronze→silver→gold row counts |
| [`query-results.csv`](query-results.csv) | csv | Query results against the governed `icu_step_down.gold.*` tables (row counts, label balance, support prevalence, census cohort) |
| [`serving-prediction.json`](serving-prediction.json) | json | Real request→response from the Mosaic AI `icu-readiness` endpoint (readiness_score + SHAP factors) |
| [`genie-conversation.md`](genie-conversation.md) | md | Genie natural-language Q&A: question → generated SQL → result rows |
| [`app-deploy.log`](app-deploy.log) | log | Deployed Databricks App RUNNING + uvicorn startup logs |
| [`drift-metrics.csv`](drift-metrics.csv) | csv | Live model-drift job output (PSI / KS vs training baseline) |
| [`execution-evidence.ipynb`](execution-evidence.ipynb) | ipynb | Notebook with committed cell outputs reproducing the above end to end |

The same content, with fuller context and how-to-reproduce, is in
[`../EVIDENCE.md`](../EVIDENCE.md) and [`../evidence/raw/`](../evidence/raw/).
The transformation logic behind it is in [`../DATA-JOURNEY.md`](../DATA-JOURNEY.md).
