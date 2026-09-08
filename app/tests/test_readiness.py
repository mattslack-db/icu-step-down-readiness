"""
Unit tests for the relative readiness index and band logic.

These are pure-function tests — no DB, no serving endpoint, no network.
"""

import pytest

from icu_step_down.backend.lib.readiness import (
    compute_readiness_index,
    readiness_band_from_index,
)


# ---------------------------------------------------------------------------
# compute_readiness_index
# ---------------------------------------------------------------------------


class TestComputeReadinessIndex:
    def test_highest_scorer_gets_near_100(self) -> None:
        scores = [0.44, 0.46, 0.48, 0.50, 0.52]
        assert compute_readiness_index(0.52, scores) == 80

    def test_lowest_scorer_gets_0(self) -> None:
        scores = [0.44, 0.46, 0.48, 0.50, 0.52]
        assert compute_readiness_index(0.44, scores) == 0

    def test_middle_scorer(self) -> None:
        scores = [0.44, 0.46, 0.48, 0.50, 0.52]
        # 0.48 has 2 scores below it out of 5 → 2/5 * 100 = 40
        assert compute_readiness_index(0.48, scores) == 40

    def test_empty_cohort_returns_50(self) -> None:
        """Empty cohort is defensive: return 50 (middle)."""
        assert compute_readiness_index(0.50, []) == 50

    def test_single_patient_returns_0(self) -> None:
        """Single patient: no others below → rank = 0."""
        assert compute_readiness_index(0.50, [0.50]) == 0

    def test_identical_scores_all_zero(self) -> None:
        """All same score: no one below → index = 0 for all."""
        scores = [0.50, 0.50, 0.50, 0.50]
        for s in scores:
            assert compute_readiness_index(s, scores) == 0

    def test_returns_int(self) -> None:
        scores = [0.44, 0.45, 0.46, 0.47]
        result = compute_readiness_index(0.46, scores)
        assert isinstance(result, int)

    def test_result_in_0_100_range(self) -> None:
        scores = [0.44 + i * 0.01 for i in range(20)]
        for s in scores:
            idx = compute_readiness_index(s, scores)
            assert 0 <= idx <= 100, f"Index {idx} out of range for score {s}"

    def test_census_of_40_patients(self) -> None:
        """Simulate realistic census: 40 scores in narrow range."""
        import random

        random.seed(42)
        scores = [0.44 + random.random() * 0.09 for _ in range(40)]
        indices = [compute_readiness_index(s, scores) for s in scores]
        # All indices must be in [0, 100]
        assert all(0 <= idx <= 100 for idx in indices)
        # Highest raw score must have highest index
        max_score = max(scores)
        max_idx = compute_readiness_index(max_score, scores)
        assert max_idx > 50  # should be near the top


# ---------------------------------------------------------------------------
# readiness_band_from_index
# ---------------------------------------------------------------------------


class TestReadinessBandFromIndex:
    @pytest.mark.parametrize(
        "index, expected",
        [
            (100, "Ready"),
            (66, "Ready"),
            (65, "Borderline"),
            (50, "Borderline"),
            (33, "Borderline"),
            (32, "Not ready"),
            (0, "Not ready"),
        ],
    )
    def test_band_boundaries(self, index: int, expected: str) -> None:
        assert readiness_band_from_index(index) == expected

    def test_returns_string(self) -> None:
        assert isinstance(readiness_band_from_index(50), str)

    def test_all_three_bands_reachable(self) -> None:
        bands = {readiness_band_from_index(i) for i in [0, 50, 100]}
        assert bands == {"Ready", "Borderline", "Not ready"}


# ---------------------------------------------------------------------------
# Integration: index → band consistency with a mock census
# ---------------------------------------------------------------------------


def test_index_band_pipeline_census_of_40():
    """
    Simulate 40 census patients.  The top 34% should be 'Ready' (roughly),
    the bottom 33% 'Not ready', and the middle 'Borderline'.
    This confirms the pipeline end-to-end with no external calls.
    """
    import random

    random.seed(0)
    scores = [0.44 + random.random() * 0.09 for _ in range(40)]
    indices = [compute_readiness_index(s, scores) for s in scores]
    bands = [readiness_band_from_index(idx) for idx in indices]

    ready_count = bands.count("Ready")
    not_ready_count = bands.count("Not ready")
    borderline_count = bands.count("Borderline")

    assert ready_count + borderline_count + not_ready_count == 40
    assert ready_count > 0, "Expected at least one Ready patient"
    assert not_ready_count > 0, "Expected at least one Not-ready patient"
