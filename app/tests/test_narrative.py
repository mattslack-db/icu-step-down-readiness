"""
Unit tests for the Gen AI narrative module.

build_narrative takes (score, factors, *, client=None) where client is
an optional callable (prompt: str) -> str.  No live Databricks needed.
"""

from __future__ import annotations

import pytest

from icu_step_down.backend.genai.narrative import (
    Factor,
    _build_prompt,
    build_narrative,
    readiness_band,
)


# ---------------------------------------------------------------------------
# readiness_band
# ---------------------------------------------------------------------------


class TestReadinessBand:
    def test_above_ready_threshold(self) -> None:
        assert readiness_band(0.75) == "Ready"
        assert readiness_band(1.0) == "Ready"
        assert readiness_band(0.80) == "Ready"

    def test_borderline_range(self) -> None:
        assert readiness_band(0.50) == "Borderline"
        assert readiness_band(0.60) == "Borderline"
        assert readiness_band(0.74) == "Borderline"

    def test_not_ready_below_threshold(self) -> None:
        assert readiness_band(0.0) == "Not ready"
        assert readiness_band(0.49) == "Not ready"

    def test_exact_boundaries(self) -> None:
        assert readiness_band(0.75) == "Ready"
        assert readiness_band(0.50) == "Borderline"


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_prompt_contains_band(self) -> None:
        factors = [Factor("last SpO₂", "supports", 0.9)]
        prompt = _build_prompt(0.8, factors)
        assert "Ready" in prompt

    def test_prompt_contains_score(self) -> None:
        factors = []
        prompt = _build_prompt(0.55, factors)
        assert "0.55" in prompt or "0.550" in prompt

    def test_factors_sorted_by_magnitude(self) -> None:
        factors = [
            Factor("minor factor", "supports", 0.1),
            Factor("major factor", "risk", 0.9),
        ]
        prompt = _build_prompt(0.5, factors)
        # Major factor should appear before minor
        pos_major = prompt.index("major factor")
        pos_minor = prompt.index("minor factor")
        assert pos_major < pos_minor

    def test_empty_factors_no_crash(self) -> None:
        prompt = _build_prompt(0.5, [])
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_not_ready_band_in_prompt(self) -> None:
        factors = [Factor("on ventilator", "risk", 0.5)]
        prompt = _build_prompt(0.3, factors)
        assert "Not ready" in prompt


# ---------------------------------------------------------------------------
# build_narrative
# ---------------------------------------------------------------------------


class TestBuildNarrative:
    def _stub(self, text: str):
        """Return a stub client that returns `text`."""
        return lambda prompt: text

    def test_returns_string(self) -> None:
        factors = [Factor("last lactate", "supports", 0.25)]
        result = build_narrative(0.8, factors, client=self._stub("Ready narrative."))
        assert isinstance(result, str)

    def test_uses_stub_response(self) -> None:
        result = build_narrative(0.8, [], client=self._stub("Stub response."))
        assert result == "Stub response."

    def test_empty_factors_ok(self) -> None:
        result = build_narrative(0.6, [], client=self._stub("Borderline."))
        assert result == "Borderline."

    def test_multiple_factors_ok(self) -> None:
        factors = [
            Factor("last SpO₂", "supports", 0.9),
            Factor("on vasopressors", "risk", 0.5),
            Factor("GCS (last)", "supports", 0.3),
        ]
        result = build_narrative(0.55, factors, client=self._stub("Multi-factor."))
        assert result == "Multi-factor."

    def test_not_ready_band(self) -> None:
        result = build_narrative(0.2, [], client=self._stub("Not ready."))
        assert result == "Not ready."

    def test_stub_receives_prompt_string(self) -> None:
        """Verify the stub is called with a non-empty string prompt."""
        received_prompts = []

        def capturing_stub(prompt: str) -> str:
            received_prompts.append(prompt)
            return "Captured."

        build_narrative(0.75, [], client=capturing_stub)
        assert len(received_prompts) == 1
        assert isinstance(received_prompts[0], str)
        assert len(received_prompts[0]) > 10

    def test_client_exception_propagates(self) -> None:
        """Errors from the client are propagated (not swallowed)."""
        def failing_stub(prompt: str) -> str:
            raise RuntimeError("LLM down")

        with pytest.raises(RuntimeError, match="LLM down"):
            build_narrative(0.8, [], client=failing_stub)

    def test_factor_dataclass(self) -> None:
        """Factor dataclass is frozen and comparable."""
        f1 = Factor("hr", "supports", 0.3)
        f2 = Factor("hr", "supports", 0.3)
        assert f1 == f2

    def test_score_hint_passed_to_prompt(self) -> None:
        """The exact score hint passed to build_narrative appears in the prompt."""
        received = []
        def capturing_stub(prompt: str) -> str:
            received.append(prompt)
            return "ok"

        build_narrative(0.90, [], client=capturing_stub)
        # 0.90 → 0.900 in prompt
        assert "0.90" in received[0] or "0.900" in received[0]
