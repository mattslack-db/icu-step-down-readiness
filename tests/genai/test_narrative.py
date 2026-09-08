"""
Unit tests for src.genai.narrative — Phase 5B Gen AI clinical narrative module.

All tests use a stub client (no network calls).  The stub echoes back the
full prompt string that build_narrative would send to the Foundation Model
endpoint.  This lets us verify:

  1. The correct readiness-band words are produced by readiness_band().
  2. The prompt passed to the FM client contains the top-magnitude factor.
  3. Factors are ordered highest-magnitude-first in the prompt.
"""

import pytest

from src.genai.narrative import Factor, build_narrative, readiness_band


# ---------------------------------------------------------------------------
# readiness_band thresholds
# ---------------------------------------------------------------------------


def test_readiness_band_thresholds() -> None:
    """Band labels map to the correct score thresholds."""
    assert readiness_band(0.92) == "Ready"
    assert readiness_band(0.75) == "Ready"       # exact boundary — inclusive
    assert readiness_band(0.60) == "Borderline"
    assert readiness_band(0.50) == "Borderline"  # exact boundary — inclusive
    assert readiness_band(0.20) == "Not ready"
    assert readiness_band(0.49) == "Not ready"   # just below borderline


# ---------------------------------------------------------------------------
# build_narrative: top factor mentioned
# ---------------------------------------------------------------------------


def test_build_narrative_mentions_top_factor() -> None:
    """
    The stub client echoes the prompt.  The echoed text must contain the
    top-magnitude factor name and must be a non-empty string.
    """
    factors = [
        Factor("off vasopressors 36h", "supports", 0.4),
        Factor("mild tachycardia", "risk", 0.1),
    ]

    def stub_client(prompt: str) -> str:
        return prompt  # echo prompt as "narrative"

    result = build_narrative(0.92, factors, client=stub_client)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "off vasopressors 36h" in result  # highest-magnitude factor


# ---------------------------------------------------------------------------
# build_narrative: factors sorted by magnitude
# ---------------------------------------------------------------------------


def test_factors_sorted_by_magnitude() -> None:
    """
    Factors are passed to the FM in descending magnitude order regardless
    of the order they arrive in the input list.
    """
    # Deliberately pass lower-magnitude factor first to confirm sorting.
    factors = [
        Factor("mild tachycardia", "risk", 0.1),         # lower magnitude
        Factor("off vasopressors 36h", "supports", 0.4), # higher magnitude
    ]

    def stub_client(prompt: str) -> str:
        return prompt

    result = build_narrative(0.55, factors, client=stub_client)

    idx_high = result.find("off vasopressors 36h")
    idx_low = result.find("mild tachycardia")

    assert idx_high != -1, "'off vasopressors 36h' not found in prompt"
    assert idx_low != -1, "'mild tachycardia' not found in prompt"
    assert idx_high < idx_low, (
        "Higher-magnitude factor should appear before lower-magnitude factor "
        f"in the prompt (got indices {idx_high} vs {idx_low})"
    )
