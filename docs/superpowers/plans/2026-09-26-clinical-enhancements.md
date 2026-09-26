# ICU Step-Down Clinical Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the readiness score into an actionable, governed, monitorable care tool by adding (1) a deterministic care-plan layer, (2) a declarative clinical-guardrail rule set backed by two new derived signals, (3) unit-level row access control, and (4) a model-drift check.

**Architecture:** Four independent phases. Deterministic Python rule layers (care plan, guardrails, drift metrics) are pure functions unit-tested in isolation; the Foundation Model only *phrases* the deterministic care plan (no invented clinical numbers). New signals and the `care_unit` dimension are computed in the Lakeflow gold layer; access control is Unity Catalog row-filter functions; drift is a scheduled DAB job comparing a persisted training baseline against appended live-score snapshots.

**Tech Stack:** Python 3.11 (FastAPI backend, pytest), Lakeflow SQL pipeline (bronze→silver→gold), Unity Catalog (row filters, grants), Databricks Foundation Model API, DABs (jobs), LightGBM/SHAP (unchanged — new signals are guardrail flags, not model inputs).

**Spec:** This plan is self-contained; the design was fixed in the 2026-09-26 brainstorming session. Decisions captured in **Design Decisions** below act as the spec.

## Design Decisions

1. **Care plan (Feature 1):** deterministic rule layer computes `next_check_in_hours` + monitoring thresholds from band + factors; the FM narrative only renders them into prose. No LLM-invented thresholds.
2. **Guardrails (Feature 2):** a declarative `CLINICAL_GUARDRAILS` registry generalizes today's `ALWAYS_RISK_FEATURES`. Two new signals — `recent_extubation` and `active_bleeding` — are **derived in gold** and carried on the census record; guardrails can either override an existing model-factor's direction (vasopressors/ventilator) or **inject a risk factor** when a derived flag is set. New signals are guardrail flags only — they are NOT added to the model's 30 features, so no retraining is required.
3. **Access control (Feature 3):** a synthetic deterministic `care_unit` (MICU/SICU/CCU) is added in gold; a Unity Catalog row-filter function bound to workspace groups restricts `census` (and `patient_features`) so each care team sees only its unit.
4. **Drift (Feature 4):** persist a training-score baseline (quantiles) once; append live census scores to `gold.readiness_score_history` on each app analytics load / scheduled snapshot; a DAB job computes PSI + KS between recent live scores and the baseline into `gold.readiness_drift`, surfaced in the Analytics view.

## Global Constraints

- **Immutability:** rule layers return new objects; never mutate inputs (frozen dataclasses).
- **No calibrated-probability language:** never emit "% chance of safe discharge"; readiness stays a relative index/band (copy rule enforced repo-wide).
- **Known-risk features always presented as risk:** vasopressors, ventilator — and now recent extubation, active bleeding — are never shown as "supports".
- **De-identified data only:** no real/identifiable patient values committed; evidence is counts/aggregates.
- **Testing:** pytest, TDD, AAA structure, ≥80% coverage on new modules (repo rule). Pipeline changes verified against the `icu-sandbox` profile.
- **Pipeline metadata loss:** gold tables are materialized views — re-run `governance.sql` AND `row_level_security.sql` after any pipeline recreate (documented in both files).
- **Deploy:** all Databricks assets via DABs (`databricks bundle deploy -t sandbox --profile icu-sandbox`).

## Review Focus

- **Care plan with an empty/low-magnitude factor list** (e.g. a patient with all-NaN vitals): `build_care_plan` must return a safe default interval + a "insufficient data — clinician review" monitoring item, not crash or emit an empty plan. → Task 1.1.
- **Guardrail flag set but feature absent from factor list** (extubation flagged, but no extubation factor from SHAP): the injected risk factor must appear exactly once and not duplicate an existing factor. → Task 2.3.
- **Row filter when a user is in no ICU unit group:** must default to deny (return no rows), never fall open to all rows. → Task 3.2.
- **Drift with fewer than N live scores** (cold start, census of 40): PSI/KS must return a documented "insufficient sample" verdict rather than a spurious drift alarm. → Task 4.2.
- **Drift baseline missing/model version mismatch:** the job must fail loud (raise), not silently compare against a stale or empty baseline. → Task 4.2.

---

## Phase 1 — Actionable Care Plan

### Task 1.1: Deterministic care-plan rule layer

**Files:**
- Create: `app/src/icu_step_down/backend/lib/care_plan.py`
- Test: `app/tests/lib/test_care_plan.py`

**Interfaces:**
- Consumes: `Factor`-like items with `.name` (raw model feature), `.direction`, `.magnitude` (the app already produces `FactorOut`; care plan takes the normalized factor tuples).
- Produces: `MonitoringItem(parameter: str, threshold: str, rationale: str)`, `CarePlan(next_check_in_hours: int, monitoring: tuple[MonitoringItem, ...], basis: str)`, and `build_care_plan(band: str, factors: list[tuple[str, str, float]]) -> CarePlan`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/lib/test_care_plan.py
from icu_step_down.backend.lib.care_plan import build_care_plan, CarePlan, MonitoringItem

def test_lactate_risk_sets_short_interval_and_lactate_threshold():
    # Arrange: borderline patient whose top risk is lactate
    factors = [("last lactate", "risk", 0.26), ("mean respiratory rate", "supports", 0.03)]
    # Act
    plan = build_care_plan("Borderline", factors)
    # Assert
    assert plan.next_check_in_hours == 6
    assert any(m.parameter == "lactate" and ">2.0" in m.threshold for m in plan.monitoring)

def test_ready_patient_gets_routine_interval():
    plan = build_care_plan("Ready", [("mean SpO₂", "supports", 0.1)])
    assert plan.next_check_in_hours == 12

def test_empty_factors_returns_safe_default_not_crash():
    plan = build_care_plan("Not ready", [])
    assert plan.next_check_in_hours == 4
    assert any("clinician review" in m.rationale.lower() for m in plan.monitoring)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && uv run pytest tests/lib/test_care_plan.py -v`
Expected: FAIL with "cannot import name 'build_care_plan'".

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/icu_step_down/backend/lib/care_plan.py
"""Deterministic care-plan layer: maps band + factors to a concrete
next-check-in interval and monitoring thresholds. The FM narrative renders
these fields into prose — it never invents them."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class MonitoringItem:
    parameter: str
    threshold: str
    rationale: str

@dataclass(frozen=True)
class CarePlan:
    next_check_in_hours: int
    monitoring: tuple[MonitoringItem, ...]
    basis: str

# Band → default reassessment interval (hours). Sicker band = tighter.
_BAND_INTERVAL = {"Ready": 12, "Borderline": 6, "Not ready": 4}

# Raw/label factor name → monitoring rule. Keyed on the normalized label
# substrings the app produces (see feature_labels.FEATURE_LABELS).
_FACTOR_RULES: dict[str, MonitoringItem] = {
    "lactate": MonitoringItem("lactate", "recheck in 6h; escalate if >2.0 mmol/L",
                              "elevated/last lactate is a top driver"),
    "heart rate": MonitoringItem("heart rate", "continuous; escalate if sustained >110 bpm",
                                 "heart-rate instability among top factors"),
    "SpO₂": MonitoringItem("SpO₂", "continuous; escalate if <92%",
                           "oxygenation among top factors"),
    "respiratory rate": MonitoringItem("respiratory rate", "hourly; escalate if >24/min",
                                       "respiratory effort among top factors"),
    "systolic BP": MonitoringItem("systolic BP", "q1h; escalate if <90 mmHg",
                                  "haemodynamics among top factors"),
    "GCS": MonitoringItem("GCS", "q2h neuro checks; escalate if drop ≥2",
                          "neurologic status among top factors"),
}

def build_care_plan(band: str, factors: list[tuple[str, str, float]]) -> CarePlan:
    interval = _BAND_INTERVAL.get(band, 4)
    monitoring: list[MonitoringItem] = []
    for label, _direction, _mag in factors:
        for key, item in _FACTOR_RULES.items():
            if key.lower() in label.lower() and item not in monitoring:
                monitoring.append(item)
    if not monitoring:
        monitoring.append(MonitoringItem(
            "vitals", "reassess full vital set at next check-in",
            "insufficient factor signal — clinician review required"))
        interval = min(interval, 4)
    return CarePlan(next_check_in_hours=interval,
                    monitoring=tuple(monitoring),
                    basis=f"band={band}; {len(factors)} factors considered")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app && uv run pytest tests/lib/test_care_plan.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/src/icu_step_down/backend/lib/care_plan.py app/tests/lib/test_care_plan.py
git commit -m "feat(care-plan): deterministic next-check-in + monitoring rule layer"
```

### Task 1.2: Feed the care plan into the narrative + patient API

**Files:**
- Modify: `src/genai/narrative.py` (`_SYSTEM_PROMPT`, `_build_prompt`, `build_narrative` signature) and mirror in `app/src/icu_step_down/backend/genai/narrative.py`
- Modify: `app/src/icu_step_down/backend/routers/patients.py` (attach care plan to the detail response)
- Modify: `app/src/icu_step_down/backend/models.py` (add `CarePlanOut` response schema)
- Test: `app/tests/genai/test_narrative_care_plan.py`, `app/tests/routers/test_patients_care_plan.py`

**Interfaces:**
- Consumes: `CarePlan` from Task 1.1; existing normalized factors.
- Produces: `build_narrative(score, factors, *, care_plan: CarePlan | None = None, client=...)`; `CarePlanOut` pydantic model with `next_check_in_hours: int` and `monitoring: list[{parameter, threshold, rationale}]`; patient detail response gains `care_plan: CarePlanOut`.

- [ ] **Step 1: Write the failing test (narrative includes plan, phrases only)**

```python
# app/tests/genai/test_narrative_care_plan.py
from icu_step_down.backend.genai.narrative import build_narrative, Factor
from icu_step_down.backend.lib.care_plan import CarePlan, MonitoringItem

def test_prompt_includes_care_plan_fields():
    captured = {}
    def stub(prompt: str) -> str:
        captured["prompt"] = prompt
        return "Borderline. Recheck lactate in 6h."
    cp = CarePlan(6, (MonitoringItem("lactate", "recheck in 6h; escalate if >2.0 mmol/L", "top driver"),), "band=Borderline")
    build_narrative(0.5, [Factor("last lactate", "risk", 0.26)], care_plan=cp, client=stub)
    assert "6h" in captured["prompt"] or "6 h" in captured["prompt"]
    assert "lactate" in captured["prompt"].lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd app && uv run pytest tests/genai/test_narrative_care_plan.py -v`
Expected: FAIL (`care_plan` is an unexpected keyword arg).

- [ ] **Step 3: Extend the prompt + signature**

In both `narrative.py` copies, extend `_SYSTEM_PROMPT` with: `" If a care plan is provided, restate its next check-in time and monitoring thresholds verbatim — do not invent new intervals, thresholds, or values."` Add `care_plan: Optional[CarePlan] = None` to `build_narrative` and, in `_build_prompt`, append when present:

```python
if care_plan is not None:
    lines = "\n".join(f"  - monitor {m.parameter}: {m.threshold} ({m.rationale})"
                      for m in care_plan.monitoring)
    prompt += (f"\n\nCare plan (restate, do not alter):\n"
               f"  - next check-in: {care_plan.next_check_in_hours}h\n{lines}")
```

- [ ] **Step 4: Write the failing API test**

```python
# app/tests/routers/test_patients_care_plan.py
def test_patient_detail_includes_care_plan(client_with_stub_db):
    resp = client_with_stub_db.get("/api/patients/224403")
    assert resp.status_code == 200
    body = resp.json()
    assert "care_plan" in body
    assert body["care_plan"]["next_check_in_hours"] in (4, 6, 12)
    assert isinstance(body["care_plan"]["monitoring"], list)
```

- [ ] **Step 5: Wire it in the router + model, run both tests**

Add `CarePlanOut` to `models.py`; in `patients.py` compute `build_care_plan(band, normalized_factors)` and include it in the response (and pass to `build_narrative`).
Run: `cd app && uv run pytest tests/genai/test_narrative_care_plan.py tests/routers/test_patients_care_plan.py -v`
Expected: all pass.

- [ ] **Step 6: Surface in the UI**

Modify `app/src/icu_step_down/ui/routes/patients/$icustay_id.tsx`: render `care_plan.next_check_in_hours` and `monitoring[]` in the existing "Recommended Actions" panel. Regenerate the API client (`apx build` runs Orval). Add/adjust a vitest assertion in the patient-detail test that the care-plan block renders.

- [ ] **Step 7: Commit**

```bash
git add app/src src/genai/narrative.py
git commit -m "feat(care-plan): surface next-check-in + thresholds in narrative, API, and patient view"
```

---

## Phase 2 — Clinical Guardrail Rule Set + Derived Signals

### Task 2.1: Derive `recent_extubation` and `active_bleeding` in gold

**Files:**
- Modify: `src/pipelines/gold.sql` (add two columns to `patient_features` and `census`)
- Modify: `src/pipelines/silver.sql` only if a needed lab (haemoglobin, INR, platelets) is not yet surfaced — verify first
- Evidence: `evidence/raw/gold-derived-signals.txt` (row counts / prevalence)

**Interfaces:**
- Produces: `patient_features.recent_extubation BOOLEAN`, `patient_features.active_bleeding BOOLEAN` (and same on `census`), consumed by Task 2.2/2.3 as census record fields.

- [ ] **Step 1: Confirm source signals exist**

Run: `databricks experimental aitools tools query "SELECT DISTINCT vital_name FROM icu_step_down.silver.vital_signs LIMIT 50" --profile icu-sandbox` and inspect `silver.lab_events` for haemoglobin/INR/platelet itemids. Record which itemids back each derived signal.

- [ ] **Step 2: Add derived columns to gold.sql**

`recent_extubation`: TRUE when a ventilator-mode reading exists earlier in the stay but the last 24h window has no ventilator reading (vent-off transition). `active_bleeding`: TRUE when last haemoglobin dropped ≥2 g/dL across the window OR INR>1.5 / platelets<50k (coagulopathy proxy). Implement as `CASE`/`LEFT JOIN` sub-selects over `silver.vital_signs` and `silver.lab_events`, keyed on `icustay_id`. Document each threshold in a SQL comment.

- [ ] **Step 3: Deploy + run the pipeline**

Run: `databricks bundle deploy -t sandbox --profile icu-sandbox` then start an update and wait for COMPLETED.

- [ ] **Step 4: Capture prevalence evidence**

```bash
databricks experimental aitools tools query "SELECT recent_extubation, active_bleeding, COUNT(*) n FROM icu_step_down.gold.patient_features GROUP BY 1,2 ORDER BY 1,2" --profile icu-sandbox | tee evidence/raw/gold-derived-signals.txt
```
Expected: the four combinations sum to 61,532; prevalences are clinically plausible (bleeding rare, extubation a minority).

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/gold.sql evidence/raw/gold-derived-signals.txt
git commit -m "feat(gold): derive recent_extubation and active_bleeding signals"
```

### Task 2.2: Declarative guardrail registry (generalize ALWAYS_RISK_FEATURES)

**Files:**
- Create: `app/src/icu_step_down/backend/lib/guardrails.py`
- Modify: `app/src/icu_step_down/backend/lib/feature_labels.py` (re-export / delegate to keep back-compat)
- Test: `app/tests/lib/test_guardrails.py`

**Interfaces:**
- Produces: `Guardrail(feature: str, kind: str, label: str, rationale: str)` where `kind ∈ {"override_risk", "inject_risk"}`; `GUARDRAILS: tuple[Guardrail, ...]`; `apply_direction_override(raw_name, direction) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/lib/test_guardrails.py
from icu_step_down.backend.lib.guardrails import GUARDRAILS, apply_direction_override

def test_vasopressors_direction_forced_to_risk():
    assert apply_direction_override("on_vasopressors", "supports") == "risk"

def test_registry_documents_extubation_and_bleeding_as_inject_risk():
    by_feature = {g.feature: g for g in GUARDRAILS}
    assert by_feature["recent_extubation"].kind == "inject_risk"
    assert by_feature["active_bleeding"].kind == "inject_risk"
    assert by_feature["on_ventilator"].kind == "override_risk"
    # every guardrail documents a clinical rationale
    assert all(g.rationale for g in GUARDRAILS)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd app && uv run pytest tests/lib/test_guardrails.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the registry**

```python
# app/src/icu_step_down/backend/lib/guardrails.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Guardrail:
    feature: str
    kind: str      # "override_risk" (model factor) | "inject_risk" (derived flag)
    label: str
    rationale: str

GUARDRAILS: tuple[Guardrail, ...] = (
    Guardrail("on_vasopressors", "override_risk", "on vasopressors",
              "haemodynamic instability never supports step-down"),
    Guardrail("on_ventilator", "override_risk", "on ventilator",
              "respiratory support never supports step-down"),
    Guardrail("recent_extubation", "inject_risk", "recently extubated (<24h)",
              "post-extubation fatigue/reintubation risk"),
    Guardrail("active_bleeding", "inject_risk", "active bleeding / coagulopathy",
              "haemorrhage risk contraindicates step-down"),
)
_OVERRIDE = {g.feature for g in GUARDRAILS if g.kind == "override_risk"}

def apply_direction_override(raw_name: str, direction: str) -> str:
    return "risk" if raw_name in _OVERRIDE else direction
```

Then in `feature_labels.py`, replace the `ALWAYS_RISK_FEATURES` check in `normalize_factor` with `direction = apply_direction_override(raw_name, direction)` and keep `ALWAYS_RISK_FEATURES` as a derived alias for back-compat.

- [ ] **Step 4: Run tests (new + existing feature_labels tests)**

Run: `cd app && uv run pytest tests/lib/test_guardrails.py tests/lib/test_feature_labels.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/src/icu_step_down/backend/lib/guardrails.py app/src/icu_step_down/backend/lib/feature_labels.py app/tests/lib/test_guardrails.py
git commit -m "feat(guardrails): declarative clinical-guardrail registry"
```

### Task 2.3: Inject derived-flag guardrails as risk factors in patient detail

**Files:**
- Modify: `app/src/icu_step_down/backend/routers/patients.py`
- Test: `app/tests/routers/test_patients_guardrails.py`

**Interfaces:**
- Consumes: `GUARDRAILS` (Task 2.2), census record fields `recent_extubation`/`active_bleeding` (Task 2.1).
- Produces: patient `top_factors` include an injected risk factor per set flag, deduplicated.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/routers/test_patients_guardrails.py
def test_active_bleeding_flag_injects_single_risk_factor(client_with_bleeding_patient):
    body = client_with_bleeding_patient.get("/api/patients/999001").json()
    labels = [f["label"] for f in body["top_factors"]]
    assert labels.count("active bleeding / coagulopathy") == 1
    assert all(f["direction"] == "risk"
               for f in body["top_factors"] if "bleeding" in f["label"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd app && uv run pytest tests/routers/test_patients_guardrails.py -v`
Expected: FAIL (no injected factor).

- [ ] **Step 3: Implement injection**

In `patients.py`, after normalizing model factors, for each `inject_risk` guardrail whose census flag is truthy, append a risk `FactorOut(label=g.label, direction="risk", magnitude=<max existing>+epsilon)` only if not already present; then re-sort and re-truncate to top-N.

- [ ] **Step 4: Run test**

Run: `cd app && uv run pytest tests/routers/test_patients_guardrails.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/src/icu_step_down/backend/routers/patients.py app/tests/routers/test_patients_guardrails.py
git commit -m "feat(guardrails): inject derived-flag risks into patient factors"
```

---

## Phase 3 — Unit-Level Row Access Control

### Task 3.1: Add synthetic `care_unit` to gold

**Files:**
- Modify: `src/pipelines/gold.sql` (add `care_unit` to `census` and `patient_features`)
- Evidence: `evidence/raw/care-unit-distribution.txt`

**Interfaces:**
- Produces: `census.care_unit STRING` ∈ {MICU, SICU, CCU} — deterministic from `icustay_id` so it is stable across pipeline re-runs.

- [ ] **Step 1: Add deterministic assignment in gold.sql**

`CASE pmod(CAST(icustay_id AS BIGINT), 3) WHEN 0 THEN 'MICU' WHEN 1 THEN 'SICU' ELSE 'CCU' END AS care_unit`. Comment that this is a synthetic demo dimension over de-identified data.

- [ ] **Step 2: Deploy + run pipeline; capture distribution**

```bash
databricks bundle deploy -t sandbox --profile icu-sandbox   # then run + wait
databricks experimental aitools tools query "SELECT care_unit, COUNT(*) n FROM icu_step_down.gold.census GROUP BY care_unit ORDER BY care_unit" --profile icu-sandbox | tee evidence/raw/care-unit-distribution.txt
```
Expected: three units, ~13-14 patients each of the 40.

- [ ] **Step 3: Commit**

```bash
git add src/pipelines/gold.sql evidence/raw/care-unit-distribution.txt
git commit -m "feat(gold): add synthetic care_unit dimension"
```

### Task 3.2: Unity Catalog row filter bound to care-team groups

**Files:**
- Create: `src/governance/row_level_security.sql`
- Modify: `README.md` (governance section note) and `src/governance/governance.sql` (cross-reference the re-run requirement)
- Evidence: `evidence/raw/row-filter.txt`

**Interfaces:**
- Produces: function `icu_step_down.gold.rls_care_unit(care_unit STRING) RETURNS BOOLEAN`; `SET ROW FILTER` on `census` and `patient_features`.

- [ ] **Step 1: Author the row-filter function (fail-closed)**

```sql
-- src/governance/row_level_security.sql
CREATE OR REPLACE FUNCTION icu_step_down.gold.rls_care_unit(care_unit STRING)
RETURN
     is_account_group_member('icu_admins')
  OR (care_unit = 'MICU' AND is_account_group_member('icu_micu'))
  OR (care_unit = 'SICU' AND is_account_group_member('icu_sicu'))
  OR (care_unit = 'CCU'  AND is_account_group_member('icu_ccu'));
-- Default deny: a user in none of these groups matches no branch → sees no rows.
ALTER TABLE icu_step_down.gold.census        SET ROW FILTER icu_step_down.gold.rls_care_unit ON (care_unit);
ALTER TABLE icu_step_down.gold.patient_features SET ROW FILTER icu_step_down.gold.rls_care_unit ON (care_unit);
```

- [ ] **Step 2: Create groups + apply; verify fail-closed and unit scoping**

Create the four account groups (or document that they exist), run the SQL, then verify: as `icu_admins` → 40 rows; as `icu_micu` → only MICU rows; as a member of no group → 0 rows. Capture outputs to `evidence/raw/row-filter.txt` (aggregate counts only).

- [ ] **Step 3: Ensure the app SP still sees its rows**

The app SP must be in `icu_admins` (or an all-units group) so the dashboard is unaffected. Add the SP to `icu_admins`; re-verify the census endpoint returns 40.

- [ ] **Step 4: Commit**

```bash
git add src/governance/row_level_security.sql src/governance/governance.sql README.md evidence/raw/row-filter.txt
git commit -m "feat(governance): unit-level row filter on census/patient_features"
```

---

## Phase 4 — Model Drift Check

### Task 4.1: Persist training baseline + live-score history

**Files:**
- Create: `src/monitoring/baseline.py` (writes `gold.readiness_training_baseline` once)
- Modify: `app/src/icu_step_down/backend/routers/analytics.py` (append snapshot to `gold.readiness_score_history` on load) OR a dedicated snapshot step in the drift job
- Evidence: `evidence/raw/drift-baseline.txt`

**Interfaces:**
- Produces: `gold.readiness_training_baseline(quantile DOUBLE, score DOUBLE, model_version STRING, computed_at TIMESTAMP)`; `gold.readiness_score_history(icustay_id STRING, readiness_score DOUBLE, model_version STRING, captured_at TIMESTAMP)`.

- [ ] **Step 1: Compute baseline quantiles from training scores**

`baseline.py` scores `gold.readiness_training_set` via the registered model (or reuses the training run's scored output), computes deciles (0.0–1.0 by 0.1), writes the baseline table with the model version. Run once; capture to `evidence/raw/drift-baseline.txt`.

- [ ] **Step 2: Append live snapshot**

Add an idempotent-per-timestamp INSERT of current census scores into `readiness_score_history` (guard against double-insert within a snapshot window). Commit.

### Task 4.2: PSI/KS drift metric + scheduled job

**Files:**
- Create: `src/monitoring/drift_check.py`
- Create: `resources/jobs.yml` (DAB job, daily schedule)
- Test: `tests/monitoring/test_drift_check.py`
- Evidence: `evidence/raw/drift-run.txt`

**Interfaces:**
- Produces: `population_stability_index(baseline: list[float], live: list[float], bins: int = 10) -> float`, `ks_statistic(baseline, live) -> float`, `drift_verdict(psi: float, n_live: int) -> str` ∈ {"insufficient", "stable", "moderate", "drift"}; writes `gold.readiness_drift(metric STRING, value DOUBLE, verdict STRING, n_live INT, model_version STRING, computed_at TIMESTAMP)`.

- [ ] **Step 1: Write failing tests (pure metric functions)**

```python
# tests/monitoring/test_drift_check.py
import pytest
from src.monitoring.drift_check import population_stability_index, drift_verdict

def test_psi_zero_for_identical_distributions():
    xs = [i/100 for i in range(100)]
    assert population_stability_index(xs, xs) == pytest.approx(0.0, abs=1e-9)

def test_psi_grows_when_distribution_shifts():
    base = [0.4 + i*0.001 for i in range(100)]
    live = [0.6 + i*0.001 for i in range(100)]
    assert population_stability_index(base, live) > 0.25

def test_verdict_insufficient_below_min_sample():
    assert drift_verdict(psi=0.9, n_live=5) == "insufficient"

def test_verdict_thresholds():
    assert drift_verdict(0.05, 200) == "stable"
    assert drift_verdict(0.15, 200) == "moderate"
    assert drift_verdict(0.30, 200) == "drift"
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/monitoring/test_drift_check.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement metrics + verdict (fail-loud on missing baseline)**

Implement PSI (binned relative-entropy style), KS (max CDF gap), and `drift_verdict` with a documented `MIN_LIVE_SAMPLE = 30` (census-aware) returning "insufficient" below it, and thresholds PSI<0.1 stable / <0.25 moderate / else drift. The job entrypoint reads baseline + recent history, and **raises** if the baseline is empty or its `model_version` differs from the served model.

- [ ] **Step 4: Run tests**

Run: `pytest tests/monitoring/test_drift_check.py -v`
Expected: 4 passed.

- [ ] **Step 5: Add the DAB job + deploy + run once**

Author `resources/jobs.yml` (serverless, daily cron, task runs `drift_check.py`). Deploy and run once; capture `gold.readiness_drift` rows to `evidence/raw/drift-run.txt`.

- [ ] **Step 6: Surface in Analytics**

Add a drift tile to `analytics.py` response + the analytics UI (latest PSI + verdict), framed as the deck's "monitorable next step". Regenerate the client; add a vitest assertion.

- [ ] **Step 7: Commit**

```bash
git add src/monitoring resources/jobs.yml tests/monitoring app/src evidence/raw/drift-run.txt evidence/raw/drift-baseline.txt
git commit -m "feat(monitoring): readiness-score drift check (PSI/KS) + scheduled job"
```

---

## Self-Review

**Spec coverage:** Feature 1 → Phase 1 (1.1 rules, 1.2 narrative/API/UI). Feature 2 → Phase 2 (2.1 derived signals, 2.2 registry, 2.3 injection). Feature 3 → Phase 3 (3.1 care_unit, 3.2 row filter). Feature 4 → Phase 4 (4.1 baseline/history, 4.2 metric/job/UI). All four decisions from the brainstorming session are implemented.

**Placeholder scan:** All code/SQL steps carry concrete content; test steps carry real assertions. Itemid lists for the derived signals (Task 2.1 Step 1) are the one runtime-discovered value and are explicitly a verify-first step, not a TODO.

**Type consistency:** `CarePlan`/`MonitoringItem` defined in 1.1, consumed by 1.2. `Guardrail`/`GUARDRAILS`/`apply_direction_override` defined in 2.2, consumed by 2.3 and by `feature_labels.normalize_factor`. `care_unit` produced in 3.1, consumed by the row filter in 3.2. `readiness_training_baseline`/`readiness_score_history` produced in 4.1, consumed by 4.2; `population_stability_index`/`drift_verdict` names consistent between test and impl.

**Review Focus:** empty-factor care plan (1.1 test), guardrail-flag-without-factor dedup (2.3 test), row-filter default-deny (3.2 Step 2), drift insufficient-sample (4.2 test), drift missing/mismatched baseline (4.2 Step 3, fail-loud) — each pinned to a task.
