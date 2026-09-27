"""
Unit tests verifying that build_narrative accepts a care_plan kwarg and
includes its fields verbatim in the prompt sent to the FM client.
"""
from icu_step_down.backend.genai.narrative import build_narrative, Factor
from icu_step_down.backend.lib.care_plan import CarePlan, MonitoringItem


def test_prompt_includes_care_plan_fields():
    captured = {}

    def stub(prompt: str) -> str:
        captured["prompt"] = prompt
        return "Borderline. Recheck lactate in 6h."

    cp = CarePlan(
        6,
        (MonitoringItem("lactate", "recheck in 6h; escalate if >2.0 mmol/L", "top driver"),),
        "band=Borderline",
    )
    build_narrative(0.5, [Factor("last lactate", "risk", 0.26)], care_plan=cp, client=stub)
    assert "6h" in captured["prompt"] or "6 h" in captured["prompt"]
    assert "lactate" in captured["prompt"].lower()
