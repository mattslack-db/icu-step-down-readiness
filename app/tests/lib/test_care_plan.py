"""
Unit tests for the deterministic care-plan rule layer.

Tests follow TDD/AAA pattern and were written BEFORE the implementation.
"""
from icu_step_down.backend.lib.care_plan import build_care_plan, CarePlan, MonitoringItem


def test_lactate_risk_sets_short_interval_and_lactate_threshold():
    # Arrange: borderline patient whose top risk is lactate
    factors = [("last lactate", "risk", 0.26), ("mean respiratory rate", "supports", 0.03)]
    # Act
    plan = build_care_plan("Borderline", factors)
    # Assert
    assert plan.next_check_in_hours == 6
    assert any(m.parameter == "lactate" and ">2.0" in m.threshold for m in plan.monitoring)


def test_ready_patient_gets_routine_interval():
    plan = build_care_plan("Ready", [("mean SpO₂", "supports", 0.1)])
    assert plan.next_check_in_hours == 12


def test_empty_factors_returns_safe_default_not_crash():
    plan = build_care_plan("Not ready", [])
    assert plan.next_check_in_hours == 4
    assert any("clinician review" in m.rationale.lower() for m in plan.monitoring)
