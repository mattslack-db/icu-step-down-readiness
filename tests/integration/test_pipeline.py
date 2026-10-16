"""
Data-pipeline integration tests — medallion invariants on real sandbox tables.

All tests are marked ``@pytest.mark.integration`` and depend on the
``sandbox_conn`` fixture (see conftest.py), which skips the whole session
when the icu-sandbox workspace is unreachable.

Run with:
    pytest tests/integration -m integration          # from repo root
    pytest tests/integration                         # same (all tests here are integration)

The default unit-test run (from app/ with ``uv run pytest``) never touches
these files.
"""

from __future__ import annotations

import pytest

def _one(conn, sql: str):
    """Execute and return the first row."""
    cur = conn.cursor()
    try:
        cur.execute(sql)
        return cur.fetchone()
    finally:
        cur.close()


# ─── Bronze layer ───────────────────────────────────────────────────────────


@pytest.mark.integration
class TestBronze:
    """Bronze core tables must have data loaded from MIMIC-III."""

    def test_patients_row_count_positive(self, sandbox_conn) -> None:
        cur = sandbox_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM icu_step_down.bronze.patients")
        count = cur.fetchone()[0]
        cur.close()
        assert count > 0, "bronze.patients is empty"

    def test_icu_stays_row_count_positive(self, sandbox_conn) -> None:
        cur = sandbox_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM icu_step_down.bronze.icu_stays")
        count = cur.fetchone()[0]
        cur.close()
        assert count > 0, "bronze.icu_stays is empty"

    def test_chart_events_scoped_row_count_positive(self, sandbox_conn) -> None:
        """Validate via silver.vital_signs which derives from chart_events."""
        cur = sandbox_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM icu_step_down.silver.vital_signs")
        count = cur.fetchone()[0]
        cur.close()
        assert count > 0, "silver.vital_signs (derived from chart_events) is empty"


# ─── Silver layer ────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestSilverVitalSigns:
    """silver.vital_signs values must fall within clinically plausible ranges."""

    def _range_check(
        self,
        sandbox_conn,
        vital_name: str,
        min_val: float,
        max_val: float,
    ) -> None:
        """Assert no rows for vital_name are outside [min_val, max_val]."""
        cur = sandbox_conn.cursor()
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM icu_step_down.silver.vital_signs
            WHERE vital_name = '{vital_name}'
              AND (
                CAST(value AS DOUBLE) < {min_val}
                OR CAST(value AS DOUBLE) > {max_val}
              )
            """
        )
        out_of_range = cur.fetchone()[0]
        cur.close()
        assert out_of_range == 0, (
            f"silver.vital_signs has {out_of_range} rows with "
            f"vital_name='{vital_name}' outside [{min_val}, {max_val}]"
        )

    def test_heart_rate_range(self, sandbox_conn) -> None:
        """Heart rate must be in [1, 350] bpm — catches raw-data corruption."""
        self._range_check(sandbox_conn, "hr", min_val=1.0, max_val=350.0)

    def test_spo2_range(self, sandbox_conn) -> None:
        """SpO2 must be in [1, 102] % — allows minor calibration artefacts."""
        self._range_check(sandbox_conn, "spo2", min_val=1.0, max_val=102.0)

    def test_temperature_range(self, sandbox_conn) -> None:
        """Body temperature must be in [25, 50] °C."""
        self._range_check(sandbox_conn, "temp_c", min_val=25.0, max_val=50.0)

    def test_gcs_range(self, sandbox_conn) -> None:
        """Glasgow Coma Scale must be in [3, 15]."""
        self._range_check(sandbox_conn, "gcs", min_val=3.0, max_val=15.0)


# ─── Gold layer — patient_features ──────────────────────────────────────────


@pytest.mark.integration
class TestGoldPatientFeatures:
    """gold.patient_features invariants."""

    def test_one_row_per_icustay_id(self, sandbox_conn) -> None:
        """Each ICU stay must appear exactly once — no duplicate feature rows."""
        cur = sandbox_conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) AS total, COUNT(DISTINCT icustay_id) AS unique_stays
            FROM icu_step_down.gold.patient_features
            """
        )
        row = cur.fetchone()
        cur.close()
        total, unique_stays = row[0], row[1]
        assert total == unique_stays, (
            f"Duplicate icustay_ids found: {total} rows, {unique_stays} distinct stays"
        )

    def test_gcs_last_null_or_valid_range(self, sandbox_conn) -> None:
        """gcs_last must be NULL or in [3, 15]."""
        cur = sandbox_conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM icu_step_down.gold.patient_features
            WHERE gcs_last IS NOT NULL
              AND (CAST(gcs_last AS INT) < 3 OR CAST(gcs_last AS INT) > 15)
            """
        )
        invalid = cur.fetchone()[0]
        cur.close()
        assert invalid == 0, (
            f"gold.patient_features has {invalid} rows with gcs_last outside [3, 15]"
        )

    def test_los_non_negative(self, sandbox_conn) -> None:
        """Length of stay must be >= 0 days."""
        cur = sandbox_conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM icu_step_down.gold.patient_features
            WHERE CAST(los AS DOUBLE) < 0
            """
        )
        invalid = cur.fetchone()[0]
        cur.close()
        assert invalid == 0, (
            f"gold.patient_features has {invalid} rows with los < 0"
        )

    def test_age_at_most_90(self, sandbox_conn) -> None:
        """Age is capped at 90 in MIMIC-III for de-identification."""
        cur = sandbox_conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM icu_step_down.gold.patient_features
            WHERE CAST(age AS DOUBLE) > 90.0
            """
        )
        invalid = cur.fetchone()[0]
        cur.close()
        assert invalid == 0, (
            f"gold.patient_features has {invalid} rows with age > 90 "
            "(MIMIC-III caps ages at 90 for de-identification)"
        )


# ─── Gold layer — readiness_training_set ─────────────────────────────────────


@pytest.mark.integration
class TestGoldReadinessTrainingSet:
    """gold.readiness_training_set invariants."""

    def test_readiness_label_binary(self, sandbox_conn) -> None:
        """readiness_label must only contain values 0 and 1 (and both must occur).
        Counted in SQL: newer connector versions return arrays as JSON strings."""
        bad, zeros, ones = _one(sandbox_conn, """
            SELECT
              SUM(CASE WHEN readiness_label NOT IN (0, 1) OR readiness_label IS NULL THEN 1 ELSE 0 END),
              SUM(CASE WHEN readiness_label = 0 THEN 1 ELSE 0 END),
              SUM(CASE WHEN readiness_label = 1 THEN 1 ELSE 0 END)
            FROM icu_step_down.gold.readiness_training_set
            """)
        assert bad == 0, f"{bad} rows with readiness_label outside {{0, 1}}"
        assert zeros > 0 and ones > 0

    def test_no_live_cohort_stays_in_training_set(self, sandbox_conn) -> None:
        """Live-cohort patients are scored as the current census and must never be trained on."""
        (overlap,) = _one(sandbox_conn, """
            SELECT COUNT(*) FROM icu_step_down.gold.readiness_training_set t
            JOIN icu_step_down.landing.live_cohort c ON c.icustay_id = t.icustay_id
            """)
        assert overlap == 0, f"{overlap} live-cohort stays leaked into the training set"

    def test_cohort_is_stays_that_left_the_icu_alive(self, sandbox_conn) -> None:
        """v4 cohort: only stays where a step-down decision was made. In-ICU deaths
        (whose last-24h window is the last day of life) and open stays are excluded."""
        excluded, died_in_icu = _one(sandbox_conn, """
            SELECT
              SUM(CASE WHEN t.label_reason IN ('died_in_icu', 'still_in_icu') THEN 1 ELSE 0 END),
              SUM(CASE WHEN s.outtime IS NULL OR s.deathtime <= s.outtime + INTERVAL 1 HOUR
                       THEN 1 ELSE 0 END)
            FROM icu_step_down.gold.readiness_training_set t
            JOIN icu_step_down.silver.icu_stays s ON s.icustay_id = t.icustay_id
            """)
        assert excluded == 0, f"{excluded} rows with an excluded label_reason"
        assert died_in_icu == 0, f"{died_in_icu} in-ICU deaths / open stays in the training set"

    def test_row_count_is_every_eligible_stay(self, sandbox_conn) -> None:
        """Nothing is dropped silently: training set = patient_features − live cohort
        − in-ICU deaths − open stays (e.g. a lossy join would shrink it)."""
        expected, actual = _one(sandbox_conn, """
            SELECT
              (SELECT COUNT(*)
                 FROM icu_step_down.gold.patient_features pf
                 JOIN icu_step_down.silver.icu_stays s ON s.icustay_id = pf.icustay_id
                 LEFT ANTI JOIN icu_step_down.landing.live_cohort c ON c.icustay_id = pf.icustay_id
                WHERE s.outtime IS NOT NULL
                  AND NOT COALESCE(s.deathtime <= s.outtime + INTERVAL 1 HOUR, FALSE)),
              (SELECT COUNT(*) FROM icu_step_down.gold.readiness_training_set)
            """)
        assert actual == expected, f"training set has {actual} rows; {expected} stays are eligible"

    def test_deaths_within_72h_are_labelled_not_safe(self, sandbox_conn) -> None:
        """Death within 72h of leaving the ICU is never 'safe'."""
        row = _one(sandbox_conn, """
            SELECT
              SUM(CASE WHEN label_reason = 'death' AND readiness_label = 1 THEN 1 ELSE 0 END),
              SUM(CASE WHEN label_reason = 'death' THEN 1 ELSE 0 END)
            FROM icu_step_down.gold.readiness_training_set
            """)
        mislabelled, deaths = row
        assert deaths > 0, "no deaths found — label_reason not populated?"
        assert mislabelled == 0, f"{mislabelled} deaths labelled as safe step-down"


# ─── Gold layer — census ─────────────────────────────────────────────────────


@pytest.mark.integration
class TestGoldCensus:
    """gold.census invariants — the 40-patient current-stay cohort."""

    def test_exactly_40_rows(self, sandbox_conn) -> None:
        """The census table must contain exactly 40 rows."""
        cur = sandbox_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM icu_step_down.gold.census")
        count = cur.fetchone()[0]
        cur.close()
        assert count == 40, f"gold.census has {count} rows, expected 40"

    def test_census_is_the_live_cohort(self, sandbox_conn) -> None:
        """While a live cohort exists, census membership is exactly that cohort."""
        row = _one(sandbox_conn, """
            SELECT
              (SELECT COUNT(*) FROM icu_step_down.landing.live_cohort) AS cohort,
              (SELECT COUNT(*) FROM icu_step_down.gold.census c
                 JOIN icu_step_down.landing.live_cohort lc ON lc.icustay_id = c.icustay_id) AS matched
            """)
        cohort, matched = row
        if cohort == 0:
            pytest.skip("no live cohort seeded — census uses the 40-most-recent fallback")
        assert matched == cohort == 40

    @pytest.mark.parametrize("column", ["hr_mean", "spo2_mean", "gcs_last"])
    def test_vitals_non_null_once_replay_complete(self, sandbox_conn, column: str) -> None:
        """Data-quality guarantee for the census — only meaningful once the live
        replay has released each stay's full final-24h window."""
        released = _one(sandbox_conn, "SELECT COALESCE(MAX(hours_released), 0) FROM icu_step_down.landing.replay_clock")[0]
        if released < 24:
            pytest.skip(f"live replay in progress ({released}h of 24h released)")
        nulls = _one(sandbox_conn, f"SELECT COUNT(*) FROM icu_step_down.gold.census WHERE {column} IS NULL")[0]
        assert nulls == 0, f"gold.census has {nulls} rows with null {column}"


# ─── PII obfuscation ─────────────────────────────────────────────────────────


@pytest.mark.integration
class TestPiiObfuscation:
    """DOB never leaves bronze; identifiers are masked / pseudonymised downstream."""

    def test_no_dob_column_in_silver_or_gold(self, sandbox_conn) -> None:
        n = _one(sandbox_conn, """
            SELECT COUNT(*) FROM icu_step_down.information_schema.columns
            WHERE table_schema IN ('silver', 'gold')
              AND LOWER(column_name) IN ('dob', 'date_of_birth', 'birth_date', 'birthdate')
            """)[0]
        assert n == 0

    def test_pipeline_pii_audit_reports_zero_forbidden_columns(self, sandbox_conn) -> None:
        assert _one(sandbox_conn, "SELECT forbidden_columns FROM icu_step_down.gold.pii_audit")[0] == 0

    def test_age_is_whole_years_capped_at_90(self, sandbox_conn) -> None:
        row = _one(sandbox_conn, """
            SELECT MAX(age_years), SUM(CASE WHEN age_years <> FLOOR(age_years) THEN 1 ELSE 0 END)
            FROM icu_step_down.silver.icu_stays
            """)
        assert row[0] <= 90 and row[1] == 0

    def test_identifiers_are_masked_for_non_admin(self, sandbox_conn) -> None:
        """The test identity is not in icu_admins, so the UC column mask applies."""
        if _one(sandbox_conn, "SELECT is_member('icu_admins')")[0]:
            pytest.skip("test identity is in icu_admins — masks return raw IDs")
        unmasked = _one(sandbox_conn, """
            SELECT COUNT(*) FROM icu_step_down.gold.census
            WHERE subject_id NOT LIKE 'P-%' OR hadm_id NOT LIKE 'P-%'
            """)[0]
        assert unmasked == 0

    @pytest.mark.parametrize("table", ["census_serving", "patient_features_serving"])
    def test_serving_tables_store_only_pseudonyms(self, sandbox_conn, table: str) -> None:
        raw = _one(sandbox_conn, f"""
            SELECT COUNT(*) FROM icu_step_down.gold.{table}
            WHERE subject_id NOT LIKE 'P-%' OR (hadm_id IS NOT NULL AND hadm_id NOT LIKE 'P-%')
            """)[0]
        assert raw == 0


# ─── Streaming ───────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestStreaming:
    """Bronze is streamed; the live cohort's final-24h window is held back."""

    @pytest.mark.parametrize("table", ["chart_events", "patients", "lab_events"])
    def test_bronze_tables_are_streaming(self, sandbox_conn, table: str) -> None:
        t = _one(sandbox_conn, f"""
            SELECT table_type FROM icu_step_down.information_schema.tables
            WHERE table_schema = 'bronze' AND table_name = '{table}'
            """)[0]
        assert t == "STREAMING_TABLE"

    def test_only_released_live_events_reach_bronze(self, sandbox_conn) -> None:
        """Cohort events inside the held-back window come ONLY from the feed."""
        row = _one(sandbox_conn, """
            SELECT
              (SELECT COUNT(*) FROM icu_step_down.bronze.chart_events ce
                 JOIN icu_step_down.landing.live_cohort lc
                   ON ce.ICUSTAY_ID = lc.icustay_id
                  AND CAST(ce.CHARTTIME AS TIMESTAMP) >= lc.window_start
                  AND CAST(ce.CHARTTIME AS TIMESTAMP) <  lc.window_end) AS in_bronze,
              (SELECT COUNT(*) FROM icu_step_down.landing.chart_events_feed) AS in_feed
            """)
        assert row[0] <= row[1], f"{row[0]} cohort-window events in bronze but only {row[1]} released"
