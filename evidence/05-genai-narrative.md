# Phase 5B — Gen AI Clinical Narrative Module

## Endpoint used

| Field | Value |
|---|---|
| Endpoint name | `databricks-meta-llama-3-3-70b-instruct` |
| Model | Meta Llama 3.3 70B Instruct (hosted by Databricks) |
| Task | `llm/v1/chat` |
| Client | `databricks.sdk.WorkspaceClient().serving_endpoints.query()` |
| Auth | Databricks SDK credential chain (`DATABRICKS_CONFIG_PROFILE=icu-sandbox`) |
| max_tokens | 300 |
| temperature | 0.2 |

## Interface implemented

```python
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass(frozen=True)
class Factor:
    name: str
    direction: str      # "supports" | "risk"
    magnitude: float

def readiness_band(score: float) -> str:
    """Ready (≥0.75) / Borderline (0.50–0.74) / Not ready (<0.50)"""

def build_narrative(
    score: float,
    factors: list[Factor],
    *,
    client: Optional[Callable[[str], str]] = None,
) -> str:
    ...
```

## Sample live narrative

**Input** — borderline patient (score 0.51, representative of training-cohort cluster ~0.44–0.53):

```python
score = 0.51
factors = [
    Factor("spo2_min",        "supports", 0.31),
    Factor("on_vasopressors", "supports", 0.28),
    Factor("hr_mean",         "risk",     0.22),
    Factor("lactate_last",    "risk",     0.19),
    Factor("gcs_last",        "supports", 0.14),
]
```

**Generated narrative** (verbatim from `databricks-meta-llama-3-3-70b-instruct`):

> The patient is currently at a Borderline readiness level for step-down transfer. The decision is supported by stable oxygen saturation levels, as evidenced by the spo2_min, and the fact that the patient is on vasopressors, which suggests some level of hemodynamic stability, as well as a relatively preserved gcs_last. However, the patient's readiness for transfer is tempered by risk factors, including an elevated hr_mean and lactate_last, which may indicate ongoing cardiovascular and metabolic stress. These competing factors contribute to the patient's borderline readiness status.

## Test results

```
pytest tests/genai/test_narrative.py -v

tests/genai/test_narrative.py::test_readiness_band_thresholds            PASSED
tests/genai/test_narrative.py::test_build_narrative_mentions_top_factor  PASSED
tests/genai/test_narrative.py::test_factors_sorted_by_magnitude          PASSED

3 passed in 0.11s
```

## Design decisions

- **No literal percentages in narrative**: the prompt instructs the model not to
  assert a numeric probability or percentage.  The score is a ranking signal, not
  a calibrated probability, so the narrative focuses on band and factors.
- **Factor sort order enforced in prompt**: `_build_prompt` sorts factors
  descending by magnitude before serialising them, so the model naturally
  leads with the most influential factors.
- **Explicit error propagation**: SDK / network errors are never swallowed;
  `RuntimeError` is raised on empty `choices` or empty content.
- **Injected client**: `build_narrative(…, client=None)` accepts a stub callable
  for testing; the real `WorkspaceClient` is constructed lazily when `client` is
  `None`.
