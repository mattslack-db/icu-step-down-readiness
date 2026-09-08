# ICU Step-Down Readiness — End-to-End Build Design

**Date:** 2026-09-08
**Status:** Approved design (pending spec review)
**Source brief:** `instructions/04-my-prompt.md` (build), `instructions/03-tech-bar.md` (requirements), `instructions/02-app-specification.md` (use case), `instructions/01-source-data.md` (data)

---

## 1. Goal & Success Criteria

Build a working, **integrated** end-to-end data journey for an ICU Step-Down Readiness use case that satisfies **Part 1 of the FE Tech Bar** (`03-tech-bar.md`). The journey must span all six stages, not siloed:

1. **Lakeflow** — ingest raw data
2. **Unity Catalog** — govern it
3. **Lakebase** — operational serving
4. **ML / Gen AI** — make it intelligent
5. **Genie Room** — natural-language querying
6. **Databricks App** — surface it to the business

**Success = a submission that passes the Build domain**, which means:

- A **public** GitHub repo under `mattslack-db` the validator can read.
- **Committed, text-readable evidence that the build ran** at every stage — notebook cells with outputs, query results, model metrics, deploy logs. Screenshots do **not** count. Source code alone does **not** pass.
- Only de-identified / public-safe data committed. No bulk raw patient rows.
- A business-outcome-led **presentation deck** (Part 2 asset).

---

## 2. Key Decisions (from brainstorming)

| Decision | Choice | Notes |
|----------|--------|-------|
| Raw data source | **Delta Share** from `hls_healthcare.mimic_iii` in `e2-demo-field-eng.cloud.databricks.com` | Cross-metastore D2D share into the sandbox. Fallback: public MIMIC-III Demo (PhysioNet). |
| Intelligence | **ML classifier + SHAP, served via Mosaic AI, PLUS a Foundation Model API Gen AI narrative** | ML gives a quantifiable readiness score + factor importance; FM API turns score+factors into a clinical summary in the app. |
| Repo visibility | **Public**, under `mattslack-db` | Validator reads it directly; safe because committed data is de-identified/aggregated. |
| Workspace | **FEVM AWS serverless sandbox**, sensible default naming/region | Created via the `fevm` MCP. |
| Deployment | **DABs** (Databricks Asset Bundles) | All Databricks assets deployed from `databricks.yml` + `resources/`. |

---

## 3. Architecture

### 3.1 Data flow (medallion)

```
hls_healthcare.mimic_iii  @ e2-demo-field-eng   ──Delta Share──►  sandbox
        │  Lakeflow declarative pipeline
        ▼
UC catalog: icu_step_down
  bronze.*   raw shared tables ingested as-is (streaming/CTAS)
  silver.*   cleaned & typed: patients, admissions, icu_stays, vital_signs, lab_events
  gold.*     patient_features (24h aggregates), readiness_training_set,
             census (current ICU patients + latest features + score)
        │  Lakebase synced tables (SNAPSHOT policy)
        ▼
Lakebase (Postgres) instance: icu-step-down     ← operational serving for the app
        │
        ├── ML: gradient-boosting readiness classifier + SHAP
        │        → MLflow registry → Mosaic AI Model Serving endpoint
        ├── Gen AI: Foundation Model API → clinical narrative from score + top SHAP factors
        ├── Genie Room over gold + silver (curated example questions)
        └── Databricks App (React / apx) — census dashboard, patient detail, analytics
```

### 3.2 Governance (Unity Catalog)

- Single catalog `icu_step_down` with schemas `bronze`, `silver`, `gold`, plus `ml` for models/functions.
- Grants documented and applied via DABs / SQL; lineage captured as evidence.
- The app reads operational data from **Lakebase**, not UC directly (per `02-spec`: Lakebase column names are case-sensitive → queries upper-cased).

### 3.3 Intelligence layer

- **Features (gold):** per-`icustay_id` 24h aggregates — HR/BP/SpO2/temp/RR means & trends, vasopressor & ventilator flags, GCS, lactate trend, LOS, age.
- **Label:** step-down readiness proxy derived from outcomes (e.g. successful transfer without ICU readmission within N hours). Documented assumptions since MIMIC is retrospective.
- **Model:** gradient boosting (sklearn/LightGBM) via `databricks-ml-training`; tracked in MLflow; SHAP for global + per-patient factor importance.
- **Serving:** Mosaic AI Model Serving endpoint.
- **Gen AI:** Foundation Model API (`databricks-ai-functions` / FM API) composes a short clinical readiness narrative from the score + top SHAP factors, surfaced in the patient detail view.

### 3.4 Genie Room

- Built over `gold.census`, `gold.patient_features`, and key `silver` tables.
- Ship a curated set of example NL questions and commit each Q → generated SQL → result as evidence.

### 3.5 Databricks App

- React app scaffolded with **apx**, implementing `02-app-specification.md`: census dashboard (summary cards, bed utilization, sortable ranked patient table), patient detail view (readiness gauge, supporting/risk factors, vitals tabs, recommended actions + the Gen AI narrative), and analytics/trends view.
- Backend (FastAPI) reads Lakebase and calls the serving endpoint + FM API.
- Deployed via DABs (`app.yml`).

---

## 4. Repo & DABs Structure

```
tech-bar/
├── databricks.yml               # DAB bundle + sandbox target
├── resources/
│   ├── pipelines.yml            # Lakeflow declarative pipeline (bronze→silver→gold)
│   ├── jobs.yml                 # training job; lakebase-sync job
│   ├── model_serving.yml        # Mosaic AI serving endpoint
│   └── app.yml                  # Databricks App resource
├── src/
│   ├── pipelines/               # ingest + transform (committed WITH cell outputs)
│   ├── ml/                      # feature eng, training, SHAP, MLflow registration
│   ├── genai/                   # FM API narrative module
│   └── genie/                   # Genie room config / example questions
├── app/                         # React Databricks App (apx scaffold)
├── scripts/                     # existing schema/DDL scripts (already present)
├── instructions/                # existing brief docs (already present)
├── docs/superpowers/specs/      # this design + future specs
└── evidence/                    # committed run outputs, query results, metrics (TEXT)
```

---

## 5. Build Order & Evidence Capture

Because scoring reads **text only**, each stage commits its run output as text (notebook cells with outputs and/or `evidence/*.md`). Build a thin working slice through the whole journey first, then deepen.

1. **Provision** — FEVM AWS serverless sandbox; public GitHub repo under `mattslack-db`; `git remote` wired up.
2. **Verify data access (FIRST, before building on it)** — confirm Delta Share from `e2-demo-field-eng` `hls_healthcare.mimic_iii` into the sandbox works. If not feasible quickly, switch to the public MIMIC-III demo (schema unchanged).
3. **Ingest (Lakeflow)** — declarative pipeline bronze→silver→gold; commit row counts + sample rows.
4. **Govern (UC)** — catalog/schemas/grants; commit `SHOW GRANTS` / lineage output.
5. **Serve (Lakebase)** — sync gold+silver to `icu-step-down`; commit connection + query results.
6. **Intelligence** — train, SHAP, register, serve; FM narrative; commit metrics + sample model output.
7. **Genie Room** — build over gold/silver; commit example NL Q → SQL → result.
8. **App** — apx React app; deploy via DABs; commit build/deploy logs.
9. **Deck** — business-outcome-led presentation (Part 2 asset).

Everything Databricks is executed through the Databricks skills (load `databricks-core` first, then the matching product skill) driving the `databricks` CLI, with `--profile` passed explicitly.

---

## 6. Risks & Fallbacks

| Risk | Mitigation |
|------|------------|
| **Cross-metastore Delta Share** from e2-demo-field-eng may not be quickly shareable to a fresh AWS sandbox metastore | Verify as step 2, before building on it. Fallback: public MIMIC-III Demo — same schema, pipeline unchanged. |
| **MIMIC-III licensing in a public repo** | Commit only de-identified aggregates / small samples as evidence; never bulk raw patient rows. |
| **Scope vs 4–8h** | Thin end-to-end slice first (all six stages minimally working), then deepen each. |
| **Lakebase case-sensitivity** | Upper-case column names in all app/serving queries per `02-spec`. |
| **Label leakage / unrealistic ML** | Document the readiness-label proxy and its assumptions; keep features causally plausible. |

---

## 7. Out of Scope

- Real-time streaming ingestion (SNAPSHOT sync is sufficient for the prototype).
- Production auth/RBAC hardening beyond sandbox defaults.
- Real patient data of any kind.
