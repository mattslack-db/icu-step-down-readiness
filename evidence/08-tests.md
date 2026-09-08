# Evidence 08 — Test Suite Results

Generated: 2026-09-08

---

## 1. Frontend Tests (vitest + @testing-library/react)

Ran: `bun run test` from `app/`

```
 ✓ src/icu_step_down/ui/__tests__/analytics.test.tsx (7 tests) 132ms
 ✓ src/icu_step_down/ui/__tests__/census.test.tsx (9 tests) 166ms
 ✓ src/icu_step_down/ui/__tests__/patient-detail.test.tsx (16 tests) 205ms

 Test Files  3 passed (3)
      Tests  32 passed (32)
   Start at  16:12:13
   Duration  1.45s (transform 212ms, setup 524ms, collect 706ms, tests 502ms, environment 1.22s, prepare 253ms)
```

### Coverage by view

| View | File | Tests | Key assertions |
|------|------|-------|----------------|
| Census | `census.test.tsx` | 9 | Heading, 3 band cards, sort controls, table present; band ≥66→Ready/🟢, 33-65→Borderline/🟡, <33→Not ready/🔴; readiness shown as index (0–100, relative) not as discharge % |
| Patient detail | `patient-detail.test.tsx` | 16 | Gauge aria-label, band label, supporting factors card, risk factors card, AI narrative (via tab click), skeleton loading state, vasopressor badge; ReadinessGauge standalone |
| Analytics | `analytics.test.tsx` | 7 | AUC-ROC 0.66 present; PR-AUC 0.98 labeled "Misleading"/class-imbalance (not headline); band distribution chart; feature importance chart; "Relative / Index, not probability" framing |

---

## 2. Backend Tests (pytest)

Ran: `uv run pytest tests/` from `app/`

```
tests/test_analytics_router.py ...............
tests/test_census_router.py ............................
tests/test_feature_labels.py ................
tests/test_lakebase.py ...
tests/test_models.py ...............
tests/test_narrative.py ..................
tests/test_readiness.py ...................
tests/test_serving_guard.py ...

117 passed in 1.11s
```

Notes:
- 114 tests existed before this task; +3 added (lakebase _build_engine_url tests)
- `TestBandDistributionViaRoute` (3 tests) replaced the inline `TestBandDistributionConcept` reimplementation — now calls the real `get_analytics` route with mocked Lakebase session and serving endpoint
- `TestBuildEngineUrl` (3 tests) covers the restored `ValueError` for APX_DEV_DB_PORT-without-password

---

## 3. Data-Pipeline Integration Tests (pytest, @pytest.mark.integration)

Ran: `pytest tests/integration -m integration -v` from repo root

```
tests/integration/test_pipeline.py::TestBronze::test_patients_row_count_positive PASSED
tests/integration/test_pipeline.py::TestBronze::test_icu_stays_row_count_positive PASSED
tests/integration/test_pipeline.py::TestBronze::test_chart_events_scoped_row_count_positive PASSED
tests/integration/test_pipeline.py::TestSilverVitalSigns::test_heart_rate_range PASSED
tests/integration/test_pipeline.py::TestSilverVitalSigns::test_spo2_range PASSED
tests/integration/test_pipeline.py::TestSilverVitalSigns::test_temperature_range PASSED
tests/integration/test_pipeline.py::TestSilverVitalSigns::test_gcs_range PASSED
tests/integration/test_pipeline.py::TestGoldPatientFeatures::test_one_row_per_icustay_id PASSED
tests/integration/test_pipeline.py::TestGoldPatientFeatures::test_gcs_last_null_or_valid_range PASSED
tests/integration/test_pipeline.py::TestGoldPatientFeatures::test_los_non_negative PASSED
tests/integration/test_pipeline.py::TestGoldPatientFeatures::test_age_at_most_90 PASSED
tests/integration/test_pipeline.py::TestGoldReadinessTrainingSet::test_readiness_label_binary PASSED
tests/integration/test_pipeline.py::TestGoldReadinessTrainingSet::test_row_count_matches_patient_features PASSED
tests/integration/test_pipeline.py::TestGoldCensus::test_exactly_40_rows PASSED
tests/integration/test_pipeline.py::TestGoldCensus::test_hr_mean_non_null PASSED
tests/integration/test_pipeline.py::TestGoldCensus::test_spo2_mean_non_null PASSED
tests/integration/test_pipeline.py::TestGoldCensus::test_gcs_last_non_null PASSED

17 passed in 43.75s
```

### Medallion invariants verified

| Layer | Table | Invariant |
|-------|-------|-----------|
| Bronze | `bronze.patients` | row count > 0 (46,520 rows) |
| Bronze | `bronze.icu_stays` | row count > 0 (61,532 rows) |
| Bronze | `silver.vital_signs` | derived from chart_events, count > 0 (via silver proxy) |
| Silver | `silver.vital_signs` | hr in [1, 350]; spo2 in [1, 102]; temp_c in [25, 50]; gcs in [3, 15] |
| Gold | `gold.patient_features` | 1 row per icustay_id (61,532 unique); gcs_last NULL or [3,15]; los ≥ 0; age ≤ 90 |
| Gold | `gold.readiness_training_set` | readiness_label ∈ {0,1}; row count == patient_features count (61,532) |
| Gold | `gold.census` | exactly 40 rows; hr_mean / spo2_mean / gcs_last all non-null |

### How to run

```bash
# Integration only (requires icu-sandbox Databricks CLI profile):
pytest tests/integration -m integration

# Skip integration (default unit run — no sandbox needed):
cd app && uv run pytest tests/
```
