# ICU Step-Down Readiness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Verification model:** This is a Databricks data/infra build, not a unit-test project. Each task's cycle is **build → run → capture committed text evidence → commit**. The "evidence" (query results, row counts, model metrics, deploy logs, saved as text in `evidence/`) IS the test, and is exactly what the tech-bar Build domain scores. Where real unit tests apply (app backend logic, the FM-narrative module), use pytest.

**Goal:** Ship an integrated, end-to-end ICU Step-Down Readiness data journey (Lakeflow → Unity Catalog → Lakebase → ML+GenAI → Genie → Databricks App) that passes Part 1 of the FE Tech Bar.

**Architecture:** MIMIC-III is Delta-shared from `e2-demo-field-eng` into a fresh FEVM AWS serverless sandbox, ingested by a Lakeflow declarative pipeline into a medallion UC catalog (`icu_step_down`), synced to a Lakebase Postgres instance for operational serving, scored by a gradient-boosting model (served via Mosaic AI) with a Foundation Model API narrative layer, made queryable via a Genie Room, and surfaced through a React Databricks App. Everything Databricks is deployed with DABs.

**Tech Stack:** Databricks (Lakeflow Declarative Pipelines, Unity Catalog, Lakebase, Mosaic AI Model Serving, Foundation Model API, Genie, Databricks Apps), DABs, `databricks` CLI, Databricks SDK for Python, MLflow, LightGBM/sklearn, SHAP, apx (React + FastAPI), Delta Sharing.

**Spec:** `docs/superpowers/specs/2026-09-08-icu-step-down-readiness-design.md`

## Global Constraints

- **Databricks skills first:** every Databricks action loads `databricks-core` then the matching product skill; drive the `databricks` CLI; always pass `--profile <name>` explicitly (never auto-select).
- **Repo:** public, under `mattslack-db`; validator must be able to read it.
- **Evidence is text:** commit notebook cells with visible outputs, query results, metrics, and logs. Screenshots do NOT count. Source code alone does NOT pass.
- **No real patient data committed:** only de-identified aggregates / small samples in `evidence/`; never bulk raw patient rows.
- **Lakebase is case-sensitive:** upper-case all column names in Postgres queries (app + serving).
- **All Databricks assets via DABs:** defined in `databricks.yml` + `resources/`.
- **Catalog:** `icu_step_down`; schemas `bronze`, `silver`, `gold`, `ml`. **Lakebase instance:** `icu-step-down`. **Source:** `hls_healthcare.mimic_iii` @ `e2-demo-field-eng`.

---

## Phase 0 — Provisioning & Foundation

### Task 0.1: Provision the FEVM AWS serverless sandbox

**Files:**
- Create: `evidence/00-provisioning.md`

**Interfaces:**
- Produces: `SANDBOX_WORKSPACE_URL`, `SANDBOX_PROFILE` (a `.databrickscfg` profile name), `DEPLOYMENT_ID` — consumed by every later task.

- [ ] **Step 1:** Load skills — `databricks-core`. Confirm the `fevm` MCP is reachable (`get_user_info`).
- [ ] **Step 2:** List FEVM templates; choose an AWS serverless sandbox template (sensible default region, e.g. us-east / us-west per catalog). Present the prefilled payload to the user and get explicit "deploy" confirmation (FEVM golden rule — never deploy without it).
- [ ] **Step 3:** On confirmation, create the deployment; poll `get_deployment` until the workspace URL is live.
- [ ] **Step 4 (evidence):** Record workspace URL, deployment ID, region, TTL into `evidence/00-provisioning.md`.
- [ ] **Step 5:** Add a `.databrickscfg` profile for the sandbox (record the profile name; do NOT commit secrets). Verify: `databricks current-user me --profile $SANDBOX_PROFILE`.
- [ ] **Step 6 (commit):** `git add evidence/00-provisioning.md && git commit -m "chore: provision FEVM AWS serverless sandbox (evidence)"`

### Task 0.2: Create the public GitHub repo and wire the remote

**Files:** none (repo metadata)

**Interfaces:**
- Produces: `origin` remote at `https://github.com/mattslack-db/<repo>`.

- [ ] **Step 1:** Choose repo name (default `icu-step-down-readiness`). Confirm the active `gh` account can create under `mattslack-db` (`gh api user`).
- [ ] **Step 2:** Create the public repo: `gh repo create mattslack-db/icu-step-down-readiness --public --source . --remote origin --push` (this pushes existing commits).
- [ ] **Step 3 (evidence/verify):** `gh repo view mattslack-db/icu-step-down-readiness --json url,visibility` → confirm `PUBLIC`. Append URL to `evidence/00-provisioning.md`.
- [ ] **Step 4 (commit):** amend `evidence/00-provisioning.md`, commit, `git push`.

### Task 0.3: Scaffold the DAB bundle

**Files:**
- Create: `databricks.yml`, `resources/.gitkeep`

**Interfaces:**
- Produces: bundle name `icu_step_down`, target `sandbox` bound to `$SANDBOX_PROFILE` / `$SANDBOX_WORKSPACE_URL`.

- [ ] **Step 1:** Load skill `databricks-dabs`.
- [ ] **Step 2:** Author `databricks.yml`: bundle name, `variables` for catalog/schema/lakebase-instance, one `targets.sandbox` (workspace host + serverless), include `resources/*.yml`.
- [ ] **Step 3 (run/verify):** `databricks bundle validate --profile $SANDBOX_PROFILE -t sandbox` → expect no errors. Save output to `evidence/00-bundle-validate.txt`.
- [ ] **Step 4 (commit):** `git add databricks.yml resources evidence && git commit -m "feat: scaffold DAB bundle for sandbox target"`

---

## Phase 1 — Data Access Verification (RISK GATE)

### Task 1.1: Establish and verify the MIMIC-III data source

**Files:**
- Create: `src/pipelines/00_verify_source.ipynb`, `evidence/01-data-access.md`

**Interfaces:**
- Produces: `SOURCE_CATALOG.SOURCE_SCHEMA` fully-qualified name reachable from the sandbox (either the shared catalog name, or the public-demo catalog if fallback taken) — consumed by Phase 2.

- [ ] **Step 1:** Load skills `databricks-core`, `databricks-unity-catalog`. From the sandbox, attempt to read the Delta Share: determine whether `hls_healthcare.mimic_iii` @ e2-demo-field-eng is reachable via an existing share or requires creating a D2D share (provider side on e2-demo-field-eng, recipient side on sandbox).
- [ ] **Step 2:** If a share must be created and the user has provider access on e2-demo-field-eng: create share + recipient, mount as catalog in sandbox. If not feasible quickly (≤ ~30 min), STOP and take the fallback: load the public MIMIC-III Clinical Database Demo into `bronze` directly (schema identical).
- [ ] **Step 3 (run/verify):** In `00_verify_source.ipynb`, run `SHOW TABLES` on the source and `SELECT COUNT(*)` on `patients`, `icu_stays`, `chart_events`; render 5 sample de-identified rows.
- [ ] **Step 4 (evidence):** Commit the notebook WITH outputs, and summarize source path + table row counts + which path (share vs fallback) into `evidence/01-data-access.md`.
- [ ] **Step 5 (decision log):** Append the chosen path to `instructions/04-my-prompt.md` decisions log.
- [ ] **Step 6 (commit):** `git add src/pipelines/00_verify_source.ipynb evidence/01-data-access.md instructions/04-my-prompt.md && git commit -m "feat: verify MIMIC-III source access (evidence)"`

---

## Phase 2 — Lakeflow Ingestion (Bronze → Silver → Gold)

### Task 2.1: Bronze ingestion pipeline

**Files:**
- Create: `resources/pipelines.yml`, `src/pipelines/bronze.sql`

**Interfaces:**
- Produces: `icu_step_down.bronze.<table>` for the core tables (patients, admissions, icu_stays, transfers, chart_events, lab_events, prescriptions, d_labitems).

- [ ] **Step 1:** Load skill `databricks-pipelines`.
- [ ] **Step 2:** Author `bronze.sql` — for each source table a `CREATE OR REFRESH STREAMING TABLE` (or `MATERIALIZED VIEW` for reference tables) selecting from the source, ingested as-is.
- [ ] **Step 3:** Define the pipeline in `resources/pipelines.yml` (serverless, target catalog `icu_step_down`, notebooks/SQL under `src/pipelines/`).
- [ ] **Step 4 (run):** `databricks bundle deploy -t sandbox --profile $SANDBOX_PROFILE` then run the pipeline; wait for completion.
- [ ] **Step 5 (evidence):** `SELECT COUNT(*)` per bronze table → `evidence/02-bronze.md`.
- [ ] **Step 6 (commit):** commit SQL, resource, and evidence.

### Task 2.2: Silver transforms

**Files:**
- Create: `src/pipelines/silver.sql`

**Interfaces:**
- Consumes: `bronze.*`.
- Produces: `silver.patients`, `silver.icu_stays`, `silver.vital_signs` (from chart_events, itemid-filtered to HR/SBP/DBP/SpO2/temp/RR), `silver.lab_events` (typed), with cleaned types and de-duplication.

- [ ] **Step 1:** Author `silver.sql` — typed, cleaned tables; map chart_events itemids to named vitals; filter to plausible ranges; dedupe on ROW_ID.
- [ ] **Step 2 (run):** redeploy + run pipeline.
- [ ] **Step 3 (evidence):** row counts + 5 sample rows of `silver.vital_signs` → `evidence/02-silver.md`.
- [ ] **Step 4 (commit):** commit.

### Task 2.3: Gold features, training set, and census

**Files:**
- Create: `src/pipelines/gold.sql`

**Interfaces:**
- Consumes: `silver.*`.
- Produces: `gold.patient_features` (per `icustay_id`: 24h means/trends of vitals, on_vasopressors, on_ventilator, gcs, lactate_trend, los, age), `gold.readiness_training_set` (features + `readiness_label`), `gold.census` (current ICU stays + latest features, ready to score).

- [ ] **Step 1:** Author `gold.sql`. Define `readiness_label` proxy: 1 if the icu_stay was discharged from ICU and NOT readmitted to ICU within 72h (via transfers/icu_stays), else 0 — document the assumption in a SQL comment.
- [ ] **Step 2 (run):** redeploy + run full pipeline bronze→silver→gold.
- [ ] **Step 3 (evidence):** row counts, label balance (`GROUP BY readiness_label`), and 5 sample feature rows → `evidence/02-gold.md`.
- [ ] **Step 4 (commit):** commit SQL + evidence. This completes a runnable ingest→features slice.

---

## Phase 3 — Unity Catalog Governance

### Task 3.1: Catalog, schemas, grants, lineage

**Files:**
- Create: `resources/uc_grants.sql` (or `src/governance/grants.sql`), `evidence/03-governance.md`

**Interfaces:**
- Consumes: existing `icu_step_down` catalog created by the pipeline.
- Produces: documented grants; lineage evidence.

- [ ] **Step 1:** Load skill `databricks-unity-catalog`.
- [ ] **Step 2:** Ensure the four schemas exist with comments; author grants (e.g. read on `gold` to the app service principal once known — parameterize).
- [ ] **Step 3 (run/verify):** run grants; `SHOW GRANTS ON SCHEMA icu_step_down.gold`; query `system.access.table_lineage` (or lineage API) for `gold.census`.
- [ ] **Step 4 (evidence):** capture `SHOW GRANTS` output + lineage rows → `evidence/03-governance.md`.
- [ ] **Step 5 (commit):** commit.

---

## Phase 4 — Lakebase Operational Serving

### Task 4.1: Lakebase instance + synced tables

**Files:**
- Create: `src/lakebase/sync_tables.ipynb`, `resources/lakebase.yml` (if DAB-manageable) , `evidence/04-lakebase.md`

**Interfaces:**
- Consumes: `gold.census`, `gold.patient_features`, `silver.vital_signs`.
- Produces: Lakebase instance `icu-step-down` with synced tables (SNAPSHOT), reachable via Postgres.

- [ ] **Step 1:** Load skill `databricks-lakebase`.
- [ ] **Step 2:** Create/confirm the `icu-step-down` Lakebase instance. Adapt the existing `scripts/create synced tables for Lakebase mimic.ipynb` to sync `gold.census`, `gold.patient_features`, `silver.vital_signs` (primary keys defined).
- [ ] **Step 3 (run):** create synced tables; wait for sync.
- [ ] **Step 4 (verify):** connect via psycopg and run an UPPER-CASED query (e.g. `SELECT COUNT(*) FROM census`); confirm rows.
- [ ] **Step 5 (evidence):** connection confirmation + query results → `evidence/04-lakebase.md` (no raw patient rows — counts/aggregates only).
- [ ] **Step 6 (commit):** commit notebook (with outputs) + evidence.

---

## Phase 5 — Intelligence (ML + Gen AI)

### Task 5.1: Training data prep + baseline model

**Files:**
- Create: `src/ml/train.ipynb`

**Interfaces:**
- Consumes: `gold.readiness_training_set`.
- Produces: trained LightGBM model logged to MLflow (run id), holdout metrics.

- [ ] **Step 1:** Load skill `databricks-ml-training`.
- [ ] **Step 2:** Load training set into a Spark/pandas frame; train/test split (stratified); train LightGBM binary classifier for `readiness_label`.
- [ ] **Step 3 (run/verify):** compute AUC, precision/recall, confusion matrix on holdout; log params/metrics/model to MLflow.
- [ ] **Step 4 (evidence):** commit notebook with metric outputs visible; summary → `evidence/05-ml-metrics.md`.
- [ ] **Step 5 (commit):** commit.

### Task 5.2: SHAP explanations

**Files:**
- Modify: `src/ml/train.ipynb` (add SHAP section)

**Interfaces:**
- Produces: global feature importance + a per-patient SHAP helper the serving/app layer reuses.

- [ ] **Step 1:** Compute SHAP values; render global importance table (matches spec's feature-importance panel).
- [ ] **Step 2 (evidence):** commit the importance ranking as text → append to `evidence/05-ml-metrics.md`.
- [ ] **Step 3 (commit):** commit.

### Task 5.3: Register model + Mosaic AI serving endpoint

**Files:**
- Create: `resources/model_serving.yml`, `src/ml/register.ipynb`

**Interfaces:**
- Consumes: MLflow run from 5.1.
- Produces: UC-registered model `icu_step_down.ml.readiness_model` + serving endpoint name `icu-readiness`.

- [ ] **Step 1:** Load skill `databricks-model-serving`.
- [ ] **Step 2:** Register the best run to UC; define the serving endpoint in `resources/model_serving.yml`.
- [ ] **Step 3 (run):** `databricks bundle deploy -t sandbox --profile $SANDBOX_PROFILE`; wait for endpoint ready.
- [ ] **Step 4 (verify):** POST a sample feature vector to the endpoint; capture the scored response.
- [ ] **Step 5 (evidence):** endpoint status + sample request/response → `evidence/05-serving.md`.
- [ ] **Step 6 (commit):** commit.

### Task 5.4: Gen AI narrative module

**Files:**
- Create: `src/genai/narrative.py`, `tests/genai/test_narrative.py`

**Interfaces:**
- Consumes: score + top SHAP factors.
- Produces: `build_narrative(score: float, factors: list[Factor]) -> str` calling the Foundation Model API; `Factor` dataclass `(name: str, direction: str, magnitude: float)`.

- [ ] **Step 1 (failing test):** write `test_narrative.py` — with a stubbed FM client, `build_narrative(0.92, [...])` returns a non-empty string mentioning the top factor. Run → FAIL.
- [ ] **Step 2 (implement):** implement `build_narrative` with a prompt template + FM API call (client injected for testability). Load skill `databricks-ai-functions` for the FM API call pattern.
- [ ] **Step 3 (verify):** run test → PASS. Then run once live against the FM API with a real sample.
- [ ] **Step 4 (evidence):** commit a live sample narrative → `evidence/05-genai-narrative.md`.
- [ ] **Step 5 (commit):** commit module + test + evidence.

---

## Phase 6 — Genie Room

### Task 6.1: Genie space + curated questions

**Files:**
- Create: `src/genie/space_config.md`, `src/genie/example_questions.md`, `evidence/06-genie.md`

**Interfaces:**
- Consumes: `gold.census`, `gold.patient_features`, `silver.vital_signs`.

- [ ] **Step 1:** Load skill `databricks-genie-agents` (or `databricks-data-discovery`).
- [ ] **Step 2:** Create a Genie space over the gold/silver tables; add table/column descriptions + example SQL to steer it.
- [ ] **Step 3 (run/verify):** ask 3–4 NL questions (e.g. "How many patients are ready for step-down?", "Show average LOS by readiness band"); capture generated SQL + results.
- [ ] **Step 4 (evidence):** commit each Q → SQL → result → `evidence/06-genie.md`.
- [ ] **Step 5 (commit):** commit config + evidence.

---

## Phase 7 — Databricks App

### Task 7.1: Scaffold the app (apx)

**Files:**
- Create: `app/` (apx scaffold), `resources/app.yml`

**Interfaces:**
- Produces: FastAPI backend + React frontend skeleton; app resource for DABs.

- [ ] **Step 1:** Load skills `databricks-apps` then `apx` (per apx MCP). Scaffold the app into `app/`.
- [ ] **Step 2 (verify):** `apx check`; run locally; confirm health route.
- [ ] **Step 3 (commit):** commit scaffold.

### Task 7.2: Backend — Lakebase + serving + narrative

**Files:**
- Create: `app/src/<slug>/routers/patients.py`, `app/src/<slug>/routers/analytics.py`
- Modify: `app/src/<slug>/app.py`

**Interfaces:**
- Consumes: Lakebase (UPPER-CASED queries), serving endpoint `icu-readiness`, `src/genai/narrative.py`.
- Produces: `GET /census`, `GET /patients/{id}`, `GET /analytics` returning typed Pydantic models.

- [ ] **Step 1 (failing test):** pytest for the census router with a mocked Lakebase client returning sample rows → asserts ranked, scored payload. Run → FAIL.
- [ ] **Step 2 (implement):** implement routers: read census/vitals from Lakebase, call serving endpoint for scores, call `build_narrative` for the detail view.
- [ ] **Step 3 (verify):** run tests → PASS; hit endpoints locally against the sandbox.
- [ ] **Step 4 (evidence):** sample JSON responses (aggregate/de-identified) → `evidence/07-app-api.md`.
- [ ] **Step 5 (commit):** commit.

### Task 7.3: Frontend — three views from the spec

**Files:**
- Create: `app/ui/src/routes/dashboard.tsx`, `.../patient-detail.tsx`, `.../analytics.tsx`

**Interfaces:**
- Consumes: generated API client.
- Produces: census dashboard (summary cards, bed-utilization bar, sortable ranked table with 🟢🟡🔴 bands), patient detail (readiness gauge, supporting/risk factors, vitals tabs, recommended actions + GenAI narrative), analytics/trends.

- [ ] **Step 1:** Implement the three routes per `02-app-specification.md` using the generated client + shadcn/ui.
- [ ] **Step 2 (verify):** run locally; walk the flows; check console clean (web-devloop-tester or Chrome DevTools MCP).
- [ ] **Step 3 (commit):** commit.

### Task 7.4: Deploy the app via DABs

**Files:**
- Modify: `resources/app.yml`

- [ ] **Step 1 (run):** `databricks bundle deploy -t sandbox --profile $SANDBOX_PROFILE`; deploy/start the app.
- [ ] **Step 2 (verify):** fetch the app URL; confirm it loads and serves live census data.
- [ ] **Step 3 (evidence):** app URL + deploy log + a curl of an API route → `evidence/07-app-deploy.md`.
- [ ] **Step 4 (commit):** commit + push.

---

## Phase 8 — Deck & Submission Packaging

### Task 8.1: Business-outcome presentation deck

**Files:**
- Create: `deck/` (or a committed PDF/HTML), link in `README.md`

**Interfaces:**
- Produces: the Part-2 presentation asset.

- [ ] **Step 1:** Load skill `databricks-slides:slide-deck` (or google-slides). Build a deck led by the business outcome, quantifying impact in the buyer's KPIs (ICU LOS reduction, bed capacity, $/day) for both executive sponsor and clinical/technical owner.
- [ ] **Step 2:** Export as shareable link / PDF / committed HTML; set access to "Anyone with the link (Viewer)" if Google Slides.
- [ ] **Step 3 (commit):** link it from `README.md`; commit.

### Task 8.2: README + submission readiness

**Files:**
- Create: `README.md`

- [ ] **Step 1:** Write `README.md`: architecture diagram, per-stage evidence links, how-to-run, data-source note (de-identified/public), and the value story.
- [ ] **Step 2 (verify):** re-read the repo as the validator would — confirm every stage has committed text evidence and the repo is public.
- [ ] **Step 3 (commit):** commit + push. Capture the build conversation ID for the optional submission field.

---

## Self-Review

**Spec coverage:** Lakeflow (P2), Unity Catalog (P3), Lakebase (P4), ML+GenAI (P5), Genie (P6), App (P7), public repo under mattslack-db (0.2), DABs (0.3 + throughout), FEVM sandbox (0.1), evidence-as-text (every task), deck (P8). All six journey stages + both submission-required artifacts covered.

**Placeholder scan:** Remaining runtime-dependent values (`SANDBOX_WORKSPACE_URL`, `SANDBOX_PROFILE`, app `<slug>`, service-principal name for grants) are defined as task **outputs/interfaces** established in Phase 0–1, not TODOs — later tasks consume them by name. The readiness-label proxy is fully specified (ICU discharge without 72h readmission).

**Type consistency:** `build_narrative(score, factors) -> str` and `Factor(name, direction, magnitude)` are used consistently across 5.4 and 7.2. Catalog/schema/instance names match the spec and Global Constraints throughout.
