# BUILD.md — how this was built, with what AI, and why

Companion to [`README.md`](README.md) (what it does + how to run) and
[`EVIDENCE.md`](EVIDENCE.md) / [`evidence/`](evidence/) (proof it ran). This file covers
the **build workflow, the AI tools and prompting approach, the key decisions and
trade-offs, and where AI was vs. was not used.**

---

## What was built (one line)

An end-to-end Databricks journey — Lakeflow medallion → Unity Catalog gold →
Mosaic AI model serving + Foundation-Model narrative → Genie → Lakebase → a
React/FastAPI Databricks App — that ranks current ICU patients by a relative
**step-down readiness index**, with governance, drift monitoring, and
unit-level access control.

## Tools used

| Tool | Role |
|------|------|
| **Claude Code** (Anthropic CLI, Claude Opus) | Primary build agent — all code, SQL, tests, and docs were authored in an interactive Claude Code session under human direction. |
| **"Superpowers" skill system** | Process discipline: `brainstorming` (idea → spec), `writing-plans` (spec → task-by-task plan), `subagent-driven-development` (fresh implementer + reviewer subagent per task), `systematic-debugging`. |
| **Databricks skills** (`databricks-core`, `-pipelines`, `-jobs`, `-lakebase`, `-model-serving`, `-apps`) | Correct CLI/DAB/Lakeflow/Lakebase/serving usage. |
| **apx** | React + FastAPI Databricks App scaffold, build, and deploy; Orval-generated typed API client. |
| **FEVM** | Sandbox workspace provisioning. |
| Review subagents (`code-reviewer`, `security-reviewer`, `python-reviewer`) | Automated review after each change. |

## Workflow (AI-assisted, spec-driven)

1. **Brainstorm → written spec** (`docs/superpowers/specs/…-design.md`): scope,
   architecture, data model, and success criteria agreed before any code.
2. **Implementation plan** (`docs/superpowers/plans/…`): the spec decomposed into
   bite-sized, independently-testable tasks (TDD steps spelled out).
3. **Subagent-driven execution**: each task implemented by a fresh subagent, then
   checked by a separate reviewer subagent (spec compliance + code quality), with
   a fix loop, then a whole-branch review at the end. Progress tracked in a ledger.
4. **TDD throughout**: tests written first; 198 backend + 37 frontend + 68
   pipeline/ML unit + 26 live integration pass (see [`evidence/test-run.log`](evidence/test-run.log)).
5. **Live verification**: pipeline, serving, Genie, Lakebase, app, drift, and
   unit-access all exercised against the sandbox; verbatim output committed
   (see [`EVIDENCE.md`](EVIDENCE.md), [`evidence/`](evidence/), [`evidence/`](evidence/)).

### Prompting approach

Prompts were **spec- and skill-driven**, not one-shot "write me an app." Each
skill sets the method (brainstorm before planning, plan before coding, tests
before implementation, review after). Representative interaction shapes:

- *"Build an ICU step-down readiness tool on Databricks"* → the brainstorming
  skill drove clarifying questions on purpose, users, and success metrics before
  proposing an architecture.
- *"Create a plan to implement \<enhancement ideas\>"* → the writing-plans skill
  produced a phased, testable plan; execution ran per-task via subagents.
- Corrective prompts (e.g. *"it didn't pass — commit readable execution evidence"*)
  drove the evidence/discoverability work.

## Key decisions and trade-offs

| Decision | Why (trade-off) |
|----------|-----------------|
| **Relative readiness index (0–100 percentile within the current census)** instead of a "probability of safe discharge" | v6 headline AUC 0.891 after label fix + new features, but readmission-only AUC 0.635 (predicting bounce-back alone is hard); a relative rank is still the safest framing. A calibrated probability would overstate precision given the readmission-only challenge. |
| **Always-flag-known-risks override**: vasopressors / ventilator are shown as `risk` regardless of the raw SHAP sign | Clinical safety — a decision-support tool must never present active life-support as "supporting discharge." Implemented in factor normalization; visible in the served-prediction evidence. |
| **Documented guardrail rule set** (`recent_extubation`, `active_bleeding` injected as risks) | Extends the same safety principle into a small, auditable rule set rather than ad-hoc checks. |
| **Delta Share MIMIC-III with a public fallback**, gated up front | De-risks the data dependency; keeps the build on public, de-identified data (no PHI). |
| **Governance via secure views** (`*_governed` + `is_member()`), not `SET ROW FILTER` | UC row filters require a table; the gold layer is materialized views, so `SET ROW FILTER` is rejected — governed views deliver the same fail-closed scoping today. |
| **App-side unit access is config-gated (default OFF), fail-closed** | The UC row filter can't reach the app's Lakebase (Postgres) path; app-side enforcement closes that gap but ships OFF so it can't lock users out before an operator verifies group setup live. |
| **Serving guard: hard-fail on prediction/patient count mismatch** | On a clinical path, silently misaligning a score to the wrong patient is unacceptable — the app raises rather than guesses. |
| **Drift monitoring (PSI/KS live vs training)** | Gives the "roadmap to stronger discrimination" a concrete, monitorable signal. |
| **Synthetic `care_unit` (MICU/SICU/CCU)** | MIMIC-III is de-identified with no real unit; a deterministic synthetic dimension enables the governance/access demo without inventing patient data. |
| **Label fix (v2→v6):** safe = alive + no readmission + no death in 72h | v2 labelled 5,274 deaths as "safe" (no readmission after leaving); corrected label separates deaths. Most of the AUC gain v2 (0.659) → v6 (0.891) comes from this fix; 23 new features add the remainder. |
| **23 new features (53 total):** last-24h labs, vitals variability, charting density, prior ICU stays, admission type, hours to ICU, surgical/cardiac ICU, male | Improved feature set on corrected training data (61,492 rows; 54,195 safe / 7,297 not safe / 5,521 deaths). |
| **PII obfuscation:** DOB dropped, age capped at 90, identifiers pseudonymized with UC column masks | HIPAA Safe Harbor compliance; Lakebase syncs pre-pseudonymized tables to avoid double-masking while keeping Postgres free of raw identifiers. |
| **Streaming pipeline in CONTINUOUS mode** | Bronze STREAMING TABLES read from Delta Share history; live cohort frozen in `landing.live_cohort`; replay job releases real historical chart events hourly. Measured latency: ~5s to bronze, ~134s to gold, ~37s Lakebase sync. |

## Where AI was — and was not — used

- **AI-generated** (under human direction, then reviewed): the Lakeflow SQL,
  feature engineering, the LightGBM model + serving wrapper, the FastAPI/React
  app, the Genie space config, tests, DABs, and all documentation.
- **Human-owned**: the product framing and clinical-safety judgments (relative
  index vs. probability, the always-risk override, what counts as a guardrail),
  scope decisions, and final review/acceptance. AI proposed; the human decided
  and verified.

## Build notes

**App build:** `apx build` (apx 0.3.8) pins `@opentelemetry/api 1.10.0-development.1` in `app/package.json` to build against prerelease OpenTelemetry. This is a transient build constraint; the OpenTelemetry API version tracks the production release lifecycle.

## Data & safety

Public, de-identified **MIMIC-III** only (Delta-shared). No secrets or real
customer data are committed (pre-commit secret scan enforced); `care_unit` is
synthetic. Only aggregate counts, metrics, and small samples appear as evidence. 
DOB is dropped in silver; identifiers are pseudonymized in gold with UC column masks.

## Presentation & demo

- **Slides:** [`deck/icu-step-down-readiness.pdf`](deck/icu-step-down-readiness.pdf)
  (source: `deck/index.html`). Per submission rules, **attach this PDF separately**
  in the submission — HTML alone is not accepted, and the repo collector excludes
  binaries so the PDF/screenshots are not picked up by the repo scan.
- **Demo recording:** _<add link here — e.g. Loom / Google Drive>_ (see
  [`evidence/RECORDING.md`](evidence/RECORDING.md)).
