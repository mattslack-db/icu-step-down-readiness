# Build Prompt & Working Notes

This document is the working brief for the ICU Step-Down Readiness build. It ties together the other instruction files and records decisions and answers as the work progresses.

## Required Reading

Read all three reference files in this folder before starting:

- `01-source-data.md` — MIMIC-III source data reference
- `02-app-specification.md` — the ICU Step-Down Readiness use case
- `03-tech-bar.md` — the build instructions to follow

---

## Objective

- Follow the instructions in `03-tech-bar.md`, **Part 1: The Build**.
- Deliver the use case described in `02-app-specification.md`.
- The source data is described in `01-source-data.md` (with more detail in the `scripts/` folder). A pipeline must be built to ingest it.
- Complete **all** requirements covered in `03-tech-bar.md`.

---

## Constraints & Environment

- **GitHub:** Store the repo under the `mattslack-db` account so it can be marked.
- **Workspace:** Use the **fevm** MCP to create a dedicated workspace, on an **AWS serverless sandbox**. Use sensible defaults for workspace naming/region preference.
- **Deployment:** Use **DABs** (Databricks Asset Bundles) to deploy the Databricks assets to the workspace.
- **Testing:** Add a comprehensive set of backend and frontend tests for the app, and integration tests for the data pipeline.

---

## Working Agreement

- Ask any questions needed along the way.
- Flag any missing details required by `03-tech-bar.md`.
- Record questions, answers, and decisions in the log below so this document stays the single source of truth.

---

## Open Questions & Decisions Log

_(Questions asked and their resolutions are captured here as work progresses.)_

- **2026-09-08 — `03-tech-bar.md` populated.** Was initially empty; now contains Part 1 (The Build) and Part 2 (roleplay) instructions. All four instruction files read.
- **2026-09-08 — Raw data source:** Delta Share the MIMIC-III data from `hls_healthcare.mimic_iii` in the `e2-demo-field-eng.cloud.databricks.com` workspace into the new sandbox. _Dependency/risk:_ requires cross-metastore Delta Sharing (D2D) from e2-demo-field-eng; fallback is the public MIMIC-III Clinical Database Demo (PhysioNet).
- **2026-09-08 — FEVM sandbox:** Use sensible defaults for workspace naming and region (AWS serverless sandbox). → Provisioned: `fe-sandbox-icu-step-down-readiness.cloud.databricks.com`, aws/us-west-2, 30-day TTL. CLI profile `icu-sandbox`.
- **2026-09-08 — GitHub repo created:** https://github.com/mattslack-db/icu-step-down-readiness (public).
- **2026-09-08 — Source confirmed:** `hls_healthcare.mimic_iii` @ `e2-demo-field-eng` (profile `DEFAULT`), 46,520 patients / 61,532 ICU stays. Delta Share `icu_step_down_mimic_iii` (23 tables) → sandbox catalog `mimic_iii_src`. Risk gate cleared, Delta Share path feasible, no fallback needed.
- **2026-09-08 — Intelligence stage:** ML classifier (readiness score) + SHAP, served via Mosaic AI, **plus** a Foundation Model API Gen AI layer that turns score + factors into a natural-language clinical summary in the app.
- **2026-09-08 — GitHub repo:** Public repo under `mattslack-db` so the tech-bar validator can read it directly.
