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
        """readiness_label must only contain values 0 and 1."""
        cur = sandbox_conn.cursor()
        cur.execute(
            """
            SELECT COLLECT_SET(readiness_label)
            FROM icu_step_down.gold.readiness_training_set
            """
        )
        label_set = set(cur.fetchone()[0])
        cur.close()
        assert label_set.issubset({0, 1}), (
            f"readiness_label contains unexpected values: {label_set - {0, 1}}"
        )

    def test_row_count_matches_patient_features(self, sandbox_conn) -> None:
        """Training set must have one row per entry in patient_features."""
        cur = sandbox_conn.cursor()
        cur.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM icu_step_down.gold.patient_features) AS pf_count,
              (SELECT COUNT(*) FROM icu_step_down.gold.readiness_training_set) AS rts_count
            """
        )
        row = cur.fetchone()
        cur.close()
        pf_count, rts_count = row[0], row[1]
        assert pf_count == rts_count, (
            f"patient_features ({pf_count} rows) != readiness_training_set ({rts_count} rows)"
        )


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

    def test_hr_mean_non_null(self, sandbox_conn) -> None:
        """Every census patient must have a non-null hr_mean (data-quality guarantee)."""
        cur = sandbox_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM icu_step_down.gold.census WHERE hr_mean IS NULL"
        )
        nulls = cur.fetchone()[0]
        cur.close()
        assert nulls == 0, f"gold.census has {nulls} rows with null hr_mean"

    def test_spo2_mean_non_null(self, sandbox_conn) -> None:
        """Every census patient must have a non-null spo2_mean."""
        cur = sandbox_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM icu_step_down.gold.census WHERE spo2_mean IS NULL"
        )
        nulls = cur.fetchone()[0]
        cur.close()
        assert nulls == 0, f"gold.census has {nulls} rows with null spo2_mean"

    def test_gcs_last_non_null(self, sandbox_conn) -> None:
        """Every census patient must have a non-null gcs_last (data-quality guarantee)."""
        cur = sandbox_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM icu_step_down.gold.census WHERE gcs_last IS NULL"
        )
        nulls = cur.fetchone()[0]
        cur.close()
        assert nulls == 0, f"gold.census has {nulls} rows with null gcs_last"
