# Architecture — ICU Step-Down Readiness

Text diagram (Mermaid) of the end-to-end, fully Databricks-native journey. One
governed gold feature set feeds the model, the app, and Genie. Committed as text
(the repo collector excludes binary images), so it is readable by reviewers.

```mermaid
flowchart LR
  subgraph Source
    M[(MIMIC-III\nDelta Share)]
  end
  subgraph Lakeflow["Lakeflow medallion (Unity Catalog)"]
    B[bronze\nraw MVs]
    S[silver\ntyped · vitals unpivot · lab flags]
    G[gold\npatient_features · readiness_training_set · census]
    B --> S --> G
  end
  subgraph ML["Mosaic AI"]
    MODEL[readiness_model v2\nLightGBM + SHAP]
    EP[[serving endpoint\nicu-readiness]]
    MODEL --> EP
  end
  FM[[Foundation Model API\nclinical narrative]]
  GEN[[Genie space\nNL → SQL]]
  LB[(Lakebase\nPostgres synced tables)]
  APP[Databricks App\nReact + FastAPI]
  DRIFT[drift job\nPSI / KS]

  M --> B
  G -->|train| MODEL
  G -->|SNAPSHOT sync| LB
  G --> GEN
  G --> DRIFT
  LB --> APP
  APP -->|feature records| EP
  EP -->|readiness_score + factors| APP
  APP --> FM
  FM --> APP
  DRIFT -->|readiness_drift| LB

  subgraph Governance
    UC[UC grants + PII tags]
    RLS[care_unit scoping\nsecure views is_member · app-side fail-closed]
  end
  UC -.governs.- G
  RLS -.governs.- G
  RLS -.governs.- APP
```

## Layer notes

- **bronze** — raw MIMIC-III tables as materialized views (Delta Share; no transform).
- **silver** — typed/cleaned; `chart_events` unpivoted to a long `vital_signs`
  stream (ITEMID→vital_name, °F→°C, physiologic range filters); `lab_events`
  `is_lactate` flag. See [`../DATA-JOURNEY.md`](../DATA-JOURNEY.md).
- **gold** — 24h feature engineering (`patient_features`) → `readiness_training_set`
  (+ 72h bounce-back label) and `census` (40 current); derived guardrail signals
  and synthetic `care_unit`.
- **serving** — LightGBM readiness model behind a Mosaic AI endpoint; returns a
  score + SHAP factors, with the always-flag-known-risks safety override.
- **narrative** — Foundation Model API turns score + factors into a clinician summary.
- **Genie** — three governed tables exposed for NL Q&A (see [`06-genie.md`](06-genie.md)).
- **Lakebase** — gold synced to Postgres (SNAPSHOT) for low-latency app reads.
- **app** — ranked census, patient detail, analytics; reads Lakebase + serving.
- **drift** — live vs training score distribution (PSI/KS) written back to gold, synced to Lakebase, surfaced in the app.
- **governance** — UC grants/PII tags + `care_unit` scoping (UC secure views via
  `is_member()`, and fail-closed app-side enforcement on the Lakebase path).
