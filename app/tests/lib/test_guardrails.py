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


# ---------------------------------------------------------------------------
# Active life support (last 24h) caps the band below "Ready"
# ---------------------------------------------------------------------------

from icu_step_down.backend.lib.guardrails import (  # noqa: E402
    active_guardrail_labels,
    cap_band,
)


def test_active_life_support_guardrails_are_registered_and_cap_ready():
    by_feature = {g.feature: g for g in GUARDRAILS}
    for feature in ("vasopressors_24h", "ventilated_24h"):
        assert by_feature[feature].kind == "inject_risk"
        assert by_feature[feature].caps_ready is True


def test_active_life_support_direction_forced_to_risk():
    """As model features, active pressors/ventilation can never 'support' readiness."""
    assert apply_direction_override("vasopressors_24h", "supports") == "risk"
    assert apply_direction_override("ventilated_24h", "supports") == "risk"


def test_ready_capped_to_borderline_when_ventilated_in_last_24h():
    assert cap_band("Ready", {"ventilated_24h": True}) == "Borderline"


def test_ready_capped_to_borderline_when_on_vasopressors_in_last_24h():
    assert cap_band("Ready", {"vasopressors_24h": "true"}) == "Borderline"


def test_cap_only_lowers_ready():
    row = {"ventilated_24h": True, "vasopressors_24h": True}
    assert cap_band("Borderline", row) == "Borderline"
    assert cap_band("Not ready", row) == "Not ready"


def test_ready_kept_without_active_life_support():
    row = {"ventilated_24h": False, "vasopressors_24h": None,
           "on_ventilator": True, "on_vasopressors": True}  # stay-level flags don't cap
    assert cap_band("Ready", row) == "Ready"


def test_active_guardrail_labels_lists_each_set_inject_flag_once():
    row = {"ventilated_24h": True, "vasopressors_24h": False, "active_bleeding": "t"}
    assert active_guardrail_labels(row) == ["active bleeding / coagulopathy", "ventilated in last 24h"]  # registry order
