"""
Unit tests for src.monitoring.drift_check — Phase 4 PSI/KS drift detection.

All tests are pure (no network / Databricks calls).  The fail-loud guard is
tested with a small stub reader injected via the function's reader arguments.

Run from repo root:
    pytest tests/monitoring/test_drift_check.py -v
"""

from __future__ import annotations

import pytest

from src.monitoring.drift_check import (
    MIN_LIVE_SAMPLE,
    drift_verdict,
    ks_statistic,
    population_stability_index,
    run_drift_check,
)


# ---------------------------------------------------------------------------
# PSI: identical distributions
# ---------------------------------------------------------------------------


def test_psi_zero_for_identical_distributions() -> None:
    """PSI is ~0 when baseline and live are the same sample."""
    xs = [i / 100 for i in range(100)]
    assert population_stability_index(xs, xs) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# PSI: shifted distribution
# ---------------------------------------------------------------------------


def test_psi_grows_when_distribution_shifts() -> None:
    """PSI exceeds 0.25 (drift threshold) when live is shifted far from base."""
    base = [0.4 + i * 0.001 for i in range(100)]
    live = [0.6 + i * 0.001 for i in range(100)]
    assert population_stability_index(base, live) > 0.25


# ---------------------------------------------------------------------------
# PSI: immutability — input lists must not be mutated
# ---------------------------------------------------------------------------


def test_psi_does_not_mutate_inputs() -> None:
    """PSI must not mutate either input list (immutability requirement)."""
    base = [0.3, 0.1, 0.5, 0.2, 0.4]
    live = [0.6, 0.7, 0.8, 0.6, 0.5]
    base_copy = list(base)
    live_copy = list(live)
    population_stability_index(base, live)
    assert base == base_copy, "population_stability_index mutated baseline"
    assert live == live_copy, "population_stability_index mutated live"


# ---------------------------------------------------------------------------
# KS: identical distributions
# ---------------------------------------------------------------------------


def test_ks_zero_for_identical_distributions() -> None:
    """KS statistic is 0 for identical distributions."""
    xs = [i / 100 for i in range(100)]
    assert ks_statistic(xs, xs) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# KS: non-overlapping distributions
# ---------------------------------------------------------------------------


def test_ks_one_for_non_overlapping() -> None:
    """KS = 1.0 when base and live do not overlap at all."""
    base = [0.1 * i for i in range(10)]  # 0.0 to 0.9
    live = [1.0 + 0.1 * i for i in range(10)]  # 1.0 to 1.9
    result = ks_statistic(base, live)
    assert result == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# drift_verdict: insufficient below MIN_LIVE_SAMPLE
# ---------------------------------------------------------------------------


def test_verdict_insufficient_below_min_sample() -> None:
    """Returns 'insufficient' when n_live < MIN_LIVE_SAMPLE, regardless of PSI."""
    assert drift_verdict(psi=0.9, n_live=5) == "insufficient"


def test_verdict_insufficient_at_min_minus_one() -> None:
    """Boundary: MIN_LIVE_SAMPLE - 1 is still insufficient."""
    assert drift_verdict(psi=0.0, n_live=MIN_LIVE_SAMPLE - 1) == "insufficient"


# ---------------------------------------------------------------------------
# drift_verdict: PSI thresholds (n_live >= MIN_LIVE_SAMPLE)
# ---------------------------------------------------------------------------


def test_verdict_thresholds() -> None:
    """PSI thresholds: <0.1 stable, 0.1–0.25 moderate, >=0.25 drift."""
    assert drift_verdict(0.05, 200) == "stable"
    assert drift_verdict(0.15, 200) == "moderate"
    assert drift_verdict(0.30, 200) == "drift"


def test_verdict_boundary_stable_to_moderate() -> None:
    """PSI exactly 0.1 is the boundary between stable and moderate."""
    assert drift_verdict(0.10, 200) == "moderate"


def test_verdict_boundary_moderate_to_drift() -> None:
    """PSI exactly 0.25 is the boundary between moderate and drift."""
    assert drift_verdict(0.25, 200) == "drift"


def test_verdict_at_exactly_min_live_sample() -> None:
    """n_live == MIN_LIVE_SAMPLE (not below it) proceeds to PSI thresholds."""
    assert drift_verdict(0.05, MIN_LIVE_SAMPLE) == "stable"


# ---------------------------------------------------------------------------
# Fail-loud guard: empty baseline
# ---------------------------------------------------------------------------


def test_run_drift_check_raises_on_empty_baseline() -> None:
    """
    run_drift_check must raise ValueError when the baseline table is empty.
    Simulates the empty-baseline guard without touching Databricks.
    """
    # Arrange
    def empty_baseline_reader():
        return {"scores": [], "model_version": "2"}

    def live_reader():
        return [0.5] * 50

    # Act / Assert
    with pytest.raises(ValueError, match="[Bb]aseline"):
        run_drift_check(
            baseline_reader=empty_baseline_reader,
            live_reader=live_reader,
            served_version="2",
        )


# ---------------------------------------------------------------------------
# Fail-loud guard: model version mismatch
# ---------------------------------------------------------------------------


def test_run_drift_check_raises_on_version_mismatch() -> None:
    """
    run_drift_check must raise ValueError when the baseline model_version
    does not match the served model version.
    """
    # Arrange
    def stale_baseline_reader():
        return {
            "scores": [0.4 + i * 0.001 for i in range(100)],
            "model_version": "1",  # stale
        }

    def live_reader():
        return [0.45 + i * 0.001 for i in range(50)]

    # Act / Assert
    with pytest.raises(ValueError, match="[Mm]odel.version|version"):
        run_drift_check(
            baseline_reader=stale_baseline_reader,
            live_reader=live_reader,
            served_version="2",  # different from baseline
        )


# ---------------------------------------------------------------------------
# run_drift_check: happy path returns expected keys
# ---------------------------------------------------------------------------


def test_run_drift_check_happy_path_returns_verdict() -> None:
    """
    When baseline is populated and versions match, run_drift_check returns
    a dict with 'psi', 'ks', 'verdict', and 'n_live'.
    """
    # Arrange
    base_scores = [0.4 + i * 0.001 for i in range(100)]

    def good_baseline_reader():
        return {"scores": base_scores, "model_version": "2"}

    def live_reader():
        return [0.41 + i * 0.001 for i in range(50)]

    # Act
    result = run_drift_check(
        baseline_reader=good_baseline_reader,
        live_reader=live_reader,
        served_version="2",
        writer=lambda _: None,  # no-op; Databricks writer not available in unit tests
    )

    # Assert
    assert "psi" in result
    assert "ks" in result
    assert "verdict" in result
    assert "n_live" in result
    assert result["n_live"] == 50
    assert result["verdict"] in {"stable", "moderate", "drift", "insufficient"}


# ---------------------------------------------------------------------------
# Writer emits BOTH a PSI row and a KS row with correct values (I-1 fix)
# ---------------------------------------------------------------------------


def test_writer_receives_both_psi_and_ks_values() -> None:
    """
    The injected writer must receive a result dict containing both 'psi' and
    'ks' with non-trivial values so that the caller can persist both metrics.
    """
    # Arrange
    base_scores = [0.4 + i * 0.001 for i in range(100)]
    live_scores = [0.42 + i * 0.001 for i in range(60)]

    written: list[dict] = []

    def capturing_writer(result: dict) -> None:
        written.append(result)

    # Act
    run_drift_check(
        baseline_reader=lambda: {"scores": base_scores, "model_version": "2"},
        live_reader=lambda: live_scores,
        served_version="2",
        writer=capturing_writer,
    )

    # Assert — writer called exactly once with a single result dict
    assert len(written) == 1
    result = written[0]

    # Both metrics must be present and finite
    assert "psi" in result, "result dict missing 'psi'"
    assert "ks" in result, "result dict missing 'ks'"
    assert isinstance(result["psi"], float), f"psi is not float: {result['psi']!r}"
    assert isinstance(result["ks"], float), f"ks is not float: {result['ks']!r}"

    # PSI and KS must be non-negative and in plausible range for a small shift
    assert result["psi"] >= 0.0, f"PSI should be non-negative, got {result['psi']}"
    assert 0.0 <= result["ks"] <= 1.0, f"KS should be in [0,1], got {result['ks']}"

    # For a slight shift (~0.02 offset), both values should be small but > 0
    assert result["psi"] > 0.0, "Expected non-zero PSI for shifted distribution"
    assert result["ks"] > 0.0, "Expected non-zero KS for shifted distribution"

    # n_live must reflect the live sample
    assert result["n_live"] == len(live_scores)
