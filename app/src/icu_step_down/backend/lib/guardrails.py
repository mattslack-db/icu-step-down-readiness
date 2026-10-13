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

``caps_ready`` (attribute)
    Active life support in the final 24h window (vasopressors, ventilation).
    The patient may still rank high on other signals, but is NEVER banded
    "Ready": the band is capped at "Borderline", the life-support factor is
    always shown as a risk, and it is injected into the factor list. The
    relative index itself is left unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


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

    caps_ready: bool = False
    """When the flag is set, the readiness band can be at most "Borderline"."""


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
    Guardrail(
        feature="vasopressors_24h",
        kind="inject_risk",
        label="vasopressors in last 24h",
        rationale="active haemodynamic support in the final 24h — not a step-down candidate yet",
        caps_ready=True,
    ),
    Guardrail(
        feature="ventilated_24h",
        kind="inject_risk",
        label="ventilated in last 24h",
        rationale="active respiratory support in the final 24h — not a step-down candidate yet",
        caps_ready=True,
    ),
)

_READY = "Ready"
_CAPPED_BAND = "Borderline"

# Internal set of features whose SHAP direction must be forced to "risk":
# explicit overrides plus the active-life-support (caps_ready) model features.
_OVERRIDE: frozenset[str] = frozenset(
    g.feature for g in GUARDRAILS if g.kind == "override_risk" or g.caps_ready
)


def _is_set(value: Any) -> bool:
    """Truthiness for flags that may arrive as bool, int, or Postgres/JSON strings."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "t", "1", "yes")
    return bool(value) if value is not None else False


def cap_band(band: str, row: Mapping[str, Any]) -> str:
    """Return the band after applying caps_ready guardrails.

    Only "Ready" is lowered (to "Borderline"); other bands are returned as-is.
    """
    if band != _READY:
        return band
    if any(g.caps_ready and _is_set(row.get(g.feature)) for g in GUARDRAILS):
        return _CAPPED_BAND
    return band


def active_guardrail_labels(row: Mapping[str, Any]) -> list[str]:
    """Labels of inject_risk guardrails whose flag is set on *row*, in registry order."""
    return [g.label for g in GUARDRAILS if g.kind == "inject_risk" and _is_set(row.get(g.feature))]


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
