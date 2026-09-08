"""
ICU Step-Down Readiness — Gen AI clinical narrative module.

Turns a readiness score and top SHAP factors into a concise (2-4 sentence)
clinician-facing natural-language summary via a Databricks Foundation Model
endpoint.

The readiness score is a *ranking signal* (not a calibrated probability);
raw scores cluster ~0.44–0.53 in the training cohort.  The narrative
describes the readiness *band* and the dominant contributing factors so
that clinicians can make an informed step-down decision.

Usage::

    from src.genai.narrative import Factor, build_narrative

    factors = [Factor("off vasopressors 36h", "supports", 0.42), ...]
    narrative = build_narrative(0.52, factors)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Factor:
    """A single SHAP-derived clinical factor from the ML model."""

    name: str
    direction: str  # "supports" | "risk"
    magnitude: float


# ---------------------------------------------------------------------------
# Readiness band helper
# ---------------------------------------------------------------------------

_THRESHOLD_READY: float = 0.75
_THRESHOLD_BORDERLINE: float = 0.50

_BAND_READY = "Ready"
_BAND_BORDERLINE = "Borderline"
_BAND_NOT_READY = "Not ready"


def readiness_band(score: float) -> str:
    """
    Map a readiness score to a clinical band label.

    Thresholds:
      - Ready      : score >= 0.75
      - Borderline : 0.50 <= score < 0.75
      - Not ready  : score < 0.50

    Args:
        score: float in [0, 1] — the model's ranking signal.

    Returns:
        One of "Ready", "Borderline", or "Not ready".
    """
    if score >= _THRESHOLD_READY:
        return _BAND_READY
    if score >= _THRESHOLD_BORDERLINE:
        return _BAND_BORDERLINE
    return _BAND_NOT_READY


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a clinical decision-support assistant helping ICU physicians."
    " Generate a concise 2-4 sentence readiness summary for a step-down"
    " transfer decision."
    " Lead with the readiness band, then describe the top supporting and risk"
    " factors."
    " Do not fabricate vital values or clinical details beyond the factors"
    " provided."
    " Do not assert a numeric probability or percentage likelihood."
    " Write in clear, clinical prose."
)


def _build_prompt(score: float, factors: list[Factor]) -> str:
    """
    Assemble the user-turn prompt from score and factors.

    Factors are sorted descending by magnitude so the most influential
    features appear first.
    """
    sorted_factors = sorted(factors, key=lambda f: f.magnitude, reverse=True)
    band = readiness_band(score)

    factor_lines = "\n".join(
        f"  - {f.name} ({f.direction}, magnitude={f.magnitude:.3f})"
        for f in sorted_factors
    )

    return (
        f"Readiness band: {band}\n"
        f"Readiness score (ranking signal, not a calibrated probability): {score:.3f}\n"
        f"Clinical factors (sorted highest-magnitude first):\n{factor_lines}\n\n"
        "Write the clinical readiness summary now."
    )


# ---------------------------------------------------------------------------
# Foundation Model endpoint configuration
# ---------------------------------------------------------------------------

_FM_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"
_FM_MAX_TOKENS = 300
_FM_TEMPERATURE = 0.2


# ---------------------------------------------------------------------------
# Real FM client construction
# ---------------------------------------------------------------------------


def _make_real_client() -> Callable[[str], str]:
    """
    Construct a live Databricks Foundation Model client using the SDK.

    Authentication is resolved by the Databricks SDK's credential chain:
    environment variables (DATABRICKS_HOST / DATABRICKS_TOKEN) or the
    profile named in DATABRICKS_CONFIG_PROFILE.  No secrets are hardcoded.

    Returns:
        A callable ``(prompt: str) -> str`` that sends a chat request to
        the Foundation Model endpoint and returns the generated text.

    Raises:
        RuntimeError: if the endpoint returns an empty or malformed response.
        Any network or authentication error from the SDK is propagated
        without suppression.
    """
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

    workspace_client = WorkspaceClient()

    def call_fm(prompt: str) -> str:
        response = workspace_client.serving_endpoints.query(
            name=_FM_ENDPOINT,
            messages=[
                ChatMessage(role=ChatMessageRole.SYSTEM, content=_SYSTEM_PROMPT),
                ChatMessage(role=ChatMessageRole.USER, content=prompt),
            ],
            max_tokens=_FM_MAX_TOKENS,
            temperature=_FM_TEMPERATURE,
        )
        choices = response.choices
        if not choices:
            raise RuntimeError(
                f"FM endpoint '{_FM_ENDPOINT}' returned an empty 'choices' list. "
                f"Full response: {response}"
            )
        content = choices[0].message.content if choices[0].message else None
        if not content:
            raise RuntimeError(
                f"FM endpoint '{_FM_ENDPOINT}' returned empty message content. "
                f"Full response: {response}"
            )
        return content

    return call_fm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_narrative(
    score: float,
    factors: list[Factor],
    *,
    client: Optional[Callable[[str], str]] = None,
) -> str:
    """
    Generate a concise clinical readiness narrative.

    Args:
        score:   Readiness score in [0, 1].  This is a *ranking signal*,
                 not a calibrated probability.  Scores cluster ~0.44–0.53
                 in the ICU step-down cohort; the narrative reports the
                 band, not the raw number.
        factors: SHAP-derived contributing factors from the ML model.
                 Any ordering is accepted — factors are sorted by magnitude
                 internally before the prompt is assembled.
        client:  Optional callable ``(prompt: str) -> str``.  When *None*
                 the real Databricks Foundation Model client is constructed
                 (auth via SDK credential chain; endpoint
                 ``databricks-meta-llama-3-3-70b-instruct``).  Inject a
                 stub for unit testing.

    Returns:
        A 2-4 sentence clinical summary string.

    Raises:
        RuntimeError: if the FM endpoint returns an empty or malformed
                      response.
        Any SDK / network exception is propagated to the caller — errors
        are never swallowed.
    """
    if client is None:
        client = _make_real_client()

    prompt = _build_prompt(score, factors)
    return client(prompt)
