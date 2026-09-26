"""
Declarative clinical-guardrail registry for the ICU Step-Down model.

Guardrails enforce two categories of clinical safety constraints:

``override_risk``
    Model features that must always be presented as "risk", regardless of the
    SHAP sign.  Being on vasopressors or a ventilator indicates haemodynamic
    or respiratory instability that never supports step-down readiness.

``inject_risk``
    Derived gold-layer flags (not model features) that, when set on a census
    row, unconditionally inject an additional risk factor into the patient's
    top-factor list.  These flags capture clinical situations that the model
    was not trained to score directly (post-extubation risk, active bleeding).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Guardrail:
    """Immutable descriptor for a single clinical guardrail rule."""

    feature: str
    """Gold-layer column name this guardrail governs."""

    kind: str
    """
    ``"override_risk"``  — force model factor direction to "risk".
    ``"inject_risk"``    — inject a synthetic risk factor when the flag is set.
    """

    label: str
    """Human-readable label for display in the UI."""

    rationale: str
    """Clinical justification; displayed in documentation and audit trails."""


GUARDRAILS: tuple[Guardrail, ...] = (
    Guardrail(
        feature="on_vasopressors",
        kind="override_risk",
        label="on vasopressors",
        rationale="haemodynamic instability never supports step-down",
    ),
    Guardrail(
        feature="on_ventilator",
        kind="override_risk",
        label="on ventilator",
        rationale="respiratory support never supports step-down",
    ),
    Guardrail(
        feature="recent_extubation",
        kind="inject_risk",
        label="recently extubated (<24h)",
        rationale="post-extubation fatigue/reintubation risk",
    ),
    Guardrail(
        feature="active_bleeding",
        kind="inject_risk",
        label="active bleeding / coagulopathy",
        rationale="haemorrhage risk contraindicates step-down",
    ),
)

# Internal set of features whose SHAP direction must be forced to "risk".
_OVERRIDE: frozenset[str] = frozenset(
    g.feature for g in GUARDRAILS if g.kind == "override_risk"
)


def apply_direction_override(raw_name: str, direction: str) -> str:
    """
    Return the corrected direction for a model feature.

    For ``override_risk`` guardrail features the direction is always ``"risk"``.
    For all other features the supplied ``direction`` is returned unchanged.

    Args:
        raw_name:  Raw feature column name (e.g. ``"on_vasopressors"``).
        direction: SHAP-derived direction (``"supports"`` | ``"risk"``).

    Returns:
        ``"risk"`` if ``raw_name`` is an override-risk guardrail, else
        ``direction`` unchanged.
    """
    return "risk" if raw_name in _OVERRIDE else direction
