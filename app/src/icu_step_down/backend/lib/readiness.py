"""
Relative readiness index and band computation.

The raw ``readiness_score`` from the model clusters in ~0.44–0.53 and is a
RANKING signal, NOT a calibrated probability.  Displaying the raw score as a
probability percentage (e.g. "52% chance of safe step-down") would be
clinically misleading.

These helpers convert the raw score to:
  1. A **relative readiness index** (0–100): the patient's percentile rank
     within the *current census* cohort.  100 = highest scorer in today's
     census.  This is suitable for both the ranked table and the gauge.
  2. A **band** derived from the index:
       - Ready      : index >= 66
       - Borderline : 33 <= index < 66
       - Not ready  : index < 33
"""

from __future__ import annotations

_BAND_READY = "Ready"
_BAND_BORDERLINE = "Borderline"
_BAND_NOT_READY = "Not ready"


def compute_readiness_index(score: float, all_scores: list[float]) -> int:
    """
    Compute the percentile rank of *score* within *all_scores* (0–100).

    The index is the fraction of census patients with a LOWER raw score,
    scaled to 0–100 and rounded to the nearest integer.

    Args:
        score:      This patient's raw readiness_score.
        all_scores: All raw scores in the current census (including this
                    patient's score so the distribution is complete).

    Returns:
        Relative readiness index in [0, 100].
    """
    n = len(all_scores)
    if n == 0:
        return 50
    rank = sum(1 for s in all_scores if s < score)
    return round((rank / n) * 100)


def readiness_band_from_index(index: int) -> str:
    """
    Derive the display band from the relative index.

    Thresholds (index-based, NOT raw-score-based):
      - Ready      : index >= 66
      - Borderline : 33 <= index < 66
      - Not ready  : index < 33

    Args:
        index: Relative readiness index (0–100).

    Returns:
        One of ``"Ready"``, ``"Borderline"``, or ``"Not ready"``.
    """
    if index >= 66:
        return _BAND_READY
    if index >= 33:
        return _BAND_BORDERLINE
    return _BAND_NOT_READY
