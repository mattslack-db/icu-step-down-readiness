# BUILD.md — how this was built, with what AI, and why

Companion to [`README.md`](README.md) (what it does + how to run) and
[`EVIDENCE.md`](EVIDENCE.md) / [`logs/`](logs/) (proof it ran). This file covers
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
4. **TDD throughout**: tests written first; 188 backend + 36 frontend + 18
   monitoring/genai pass (see [`logs/test-run.log`](logs/test-run.log)).
5. **Live verification**: pipeline, serving, Genie, Lakebase, app, drift, and
   unit-access all exercised against the sandbox; verbatim output committed
   (see [`EVIDENCE.md`](EVIDENCE.md), [`logs/`](logs/), [`evidence/raw/`](evidence/raw/)).

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
| **Relative readiness index (0–100 percentile within the current census)** instead of a "probability of safe discharge" | The model's discrimination is modest (AUC ≈ 0.66); a calibrated probability would be misleading. A relative rank is honest and still actionable. |
| **Always-flag-known-risks override**: vasopressors / ventilator are shown as `risk` regardless of the raw SHAP sign | Clinical safety — a decision-support tool must never present active life-support as "supporting discharge." Implemented in factor normalization; visible in the served-prediction evidence. |
| **Documented guardrail rule set** (`recent_extubation`, `active_bleeding` injected as risks) | Extends the same safety principle into a small, auditable rule set rather than ad-hoc checks. |
| **Delta Share MIMIC-III with a public fallback**, gated up front | De-risks the data dependency; keeps the build on public, de-identified data (no PHI). |
| **Governance via secure views** (`*_governed` + `is_member()`), not `SET ROW FILTER` | UC row filters require a table; the gold layer is materialized views, so `SET ROW FILTER` is rejected — governed views deliver the same fail-closed scoping today. |
| **App-side unit access is config-gated (default OFF), fail-closed** | The UC row filter can't reach the app's Lakebase (Postgres) path; app-side enforcement closes that gap but ships OFF so it can't lock users out before an operator verifies group setup live. |
| **Serving guard: hard-fail on prediction/patient count mismatch** | On a clinical path, silently misaligning a score to the wrong patient is unacceptable — the app raises rather than guesses. |
| **Drift monitoring (PSI/KS live vs training)** | Gives the "roadmap to stronger discrimination" a concrete, monitorable signal. |
| **Synthetic `care_unit` (MICU/SICU/CCU)** | MIMIC-III is de-identified with no real unit; a deterministic synthetic dimension enables the governance/access demo without inventing patient data. |

## Where AI was — and was not — used

- **AI-generated** (under human direction, then reviewed): the Lakeflow SQL,
  feature engineering, the LightGBM model + serving wrapper, the FastAPI/React
  app, the Genie space config, tests, DABs, and all documentation.
- **Human-owned**: the product framing and clinical-safety judgments (relative
  index vs. probability, the always-risk override, what counts as a guardrail),
  scope decisions, and final review/acceptance. AI proposed; the human decided
  and verified.

## Data & safety

Public, de-identified **MIMIC-III** only (Delta-shared). No secrets or real
customer data are committed (pre-commit secret scan enforced); `care_unit` is
synthetic. Only aggregate counts, metrics, and small samples appear as evidence.

## Presentation & demo

- **Slides:** [`deck/icu-step-down-readiness.pdf`](deck/icu-step-down-readiness.pdf)
  (source: `deck/index.html`). Per submission rules, **attach this PDF separately**
  in the submission — HTML alone is not accepted, and the repo collector excludes
  binaries so the PDF/screenshots are not picked up by the repo scan.
- **Demo recording:** _<add link here — e.g. Loom / Google Drive>_ (see
  [`evidence/RECORDING.md`](evidence/RECORDING.md)).
