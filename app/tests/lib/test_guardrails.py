"""
Unit tests for the declarative clinical-guardrail registry.

Tests verify:
- apply_direction_override forces "risk" for override_risk features
- GUARDRAILS contains expected entries with correct kinds
- Every guardrail documents a non-empty clinical rationale
"""
from __future__ import annotations

from icu_step_down.backend.lib.guardrails import GUARDRAILS, apply_direction_override


def test_vasopressors_direction_forced_to_risk():
    assert apply_direction_override("on_vasopressors", "supports") == "risk"


def test_ventilator_direction_forced_to_risk():
    assert apply_direction_override("on_ventilator", "supports") == "risk"


def test_override_already_risk_unchanged():
    # Idempotent: already "risk" stays "risk"
    assert apply_direction_override("on_vasopressors", "risk") == "risk"


def test_non_override_feature_direction_preserved():
    # inject_risk features do NOT override direction via apply_direction_override
    assert apply_direction_override("recent_extubation", "supports") == "supports"
    assert apply_direction_override("active_bleeding", "supports") == "supports"


def test_unknown_feature_direction_preserved():
    assert apply_direction_override("spo2_min", "supports") == "supports"
    assert apply_direction_override("lactate_last", "risk") == "risk"


def test_registry_documents_extubation_and_bleeding_as_inject_risk():
    by_feature = {g.feature: g for g in GUARDRAILS}
    assert by_feature["recent_extubation"].kind == "inject_risk"
    assert by_feature["active_bleeding"].kind == "inject_risk"
    assert by_feature["on_ventilator"].kind == "override_risk"
    # every guardrail documents a clinical rationale
    assert all(g.rationale for g in GUARDRAILS)


def test_guardrail_dataclass_is_frozen():
    """Guardrail instances must be immutable (frozen=True)."""
    import dataclasses
    g = next(iter(GUARDRAILS))
    assert dataclasses.is_dataclass(g)
    try:
        g.feature = "mutated"  # type: ignore[misc]
        raise AssertionError("Expected FrozenInstanceError")
    except (dataclasses.FrozenInstanceError, AttributeError):
        pass  # expected


def test_guardrail_labels_are_non_empty():
    for g in GUARDRAILS:
        assert isinstance(g.label, str) and g.label, f"Empty label for {g.feature!r}"


def test_guardrail_kinds_are_valid():
    valid_kinds = {"override_risk", "inject_risk"}
    for g in GUARDRAILS:
        assert g.kind in valid_kinds, f"Unknown kind {g.kind!r} for {g.feature!r}"
