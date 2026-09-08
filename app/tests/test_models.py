"""
Unit tests for Pydantic response models.

Validates that models accept valid data, reject invalid data, and that
optional/nullable fields work as documented.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from icu_step_down.backend.models import (
    AnalyticsResponse,
    BandCount,
    CensusPatient,
    CensusResponse,
    FactorOut,
    FeatureImportanceItem,
    PatientDetail,
    PatientFeatures,
    VitalPoint,
)


# ---------------------------------------------------------------------------
# FactorOut
# ---------------------------------------------------------------------------


class TestFactorOut:
    def test_valid_supports(self) -> None:
        f = FactorOut(name="last lactate", direction="supports", magnitude=0.25)
        assert f.direction == "supports"

    def test_valid_risk(self) -> None:
        f = FactorOut(name="on ventilator", direction="risk", magnitude=0.5)
        assert f.direction == "risk"

    def test_missing_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            FactorOut(direction="risk", magnitude=0.1)  # type: ignore[call-arg]

    def test_missing_magnitude_raises(self) -> None:
        with pytest.raises(ValidationError):
            FactorOut(name="x", direction="risk")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# CensusPatient
# ---------------------------------------------------------------------------


class TestCensusPatient:
    def _minimal(self) -> dict:
        return {
            "icustay_id": "123",
            "subject_id": "456",
            "age": 65.0,
            "los": 2.5,
            "readiness_score": 0.55,
            "readiness_index": 70,
            "band": "Ready",
            "on_vasopressors": False,
            "on_ventilator": False,
            "top_factors": [],
        }

    def test_valid_patient(self) -> None:
        p = CensusPatient(**self._minimal())
        assert p.readiness_index == 70
        assert p.band == "Ready"

    def test_with_factors(self) -> None:
        data = self._minimal()
        data["top_factors"] = [
            {"name": "lactate_last", "direction": "supports", "magnitude": 0.3}
        ]
        p = CensusPatient(**data)
        assert len(p.top_factors) == 1

    def test_missing_icustay_raises(self) -> None:
        data = self._minimal()
        del data["icustay_id"]
        with pytest.raises(ValidationError):
            CensusPatient(**data)

    def test_bool_fields(self) -> None:
        data = self._minimal()
        data["on_vasopressors"] = True
        data["on_ventilator"] = True
        p = CensusPatient(**data)
        assert p.on_vasopressors is True
        assert p.on_ventilator is True


# ---------------------------------------------------------------------------
# CensusResponse
# ---------------------------------------------------------------------------


class TestCensusResponse:
    def test_empty_census(self) -> None:
        r = CensusResponse(patients=[], total=0, generated_at="2026-09-08T12:00:00Z")
        assert r.total == 0
        assert r.patients == []

    def test_total_matches_patients(self) -> None:
        """No enforcement in model, but correct usage should have them equal."""
        from icu_step_down.backend.models import CensusPatient
        p_data = {
            "icustay_id": "1", "subject_id": "2", "age": 50.0, "los": 1.0,
            "readiness_score": 0.6, "readiness_index": 80, "band": "Ready",
            "on_vasopressors": False, "on_ventilator": False, "top_factors": [],
        }
        r = CensusResponse(
            patients=[CensusPatient(**p_data)],
            total=1,
            generated_at="2026-09-08T12:00:00Z",
        )
        assert r.total == len(r.patients)


# ---------------------------------------------------------------------------
# PatientFeatures
# ---------------------------------------------------------------------------


class TestPatientFeatures:
    def test_nullable_vitals(self) -> None:
        """All vital mean fields are optional (nullable)."""
        pf = PatientFeatures(
            icustay_id="123",
            subject_id="456",
            age=65.0,
            los=2.5,
            on_vasopressors=False,
            on_ventilator=False,
            hr_mean=None,
            sbp_mean=None,
            dbp_mean=None,
            spo2_mean=None,
            spo2_min=None,
            temp_c_mean=None,
            rr_mean=None,
            gcs_last=None,
            lactate_last=None,
        )
        assert pf.gcs_last is None
        assert pf.lactate_last is None

    def test_with_all_vitals(self) -> None:
        pf = PatientFeatures(
            icustay_id="123",
            subject_id="456",
            age=65.0,
            los=2.5,
            on_vasopressors=True,
            on_ventilator=False,
            hr_mean=80.0,
            sbp_mean=120.0,
            dbp_mean=70.0,
            spo2_mean=97.0,
            spo2_min=94.0,
            temp_c_mean=37.2,
            rr_mean=16.0,
            gcs_last=15.0,
            lactate_last=1.2,
        )
        assert pf.gcs_last == pytest.approx(15.0)
        assert pf.lactate_last == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# VitalPoint
# ---------------------------------------------------------------------------


class TestVitalPoint:
    def test_valid_vital_point(self) -> None:
        vp = VitalPoint(
            charttime="2026-09-08T10:00:00",
            vital_name="hr",
            value=80.0,
        )
        assert vp.vital_name == "hr"
        assert vp.value == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# AnalyticsResponse
# ---------------------------------------------------------------------------


class TestAnalyticsResponse:
    def test_valid_analytics_response(self) -> None:
        r = AnalyticsResponse(
            total_census=40,
            band_distribution=[
                BandCount(band="Ready", count=13, pct=32.5),
                BandCount(band="Borderline", count=13, pct=32.5),
                BandCount(band="Not ready", count=14, pct=35.0),
            ],
            feature_importance=[
                FeatureImportanceItem(feature="last lactate", importance=0.246)
            ],
            avg_los_by_band={"Ready": 2.71, "Borderline": 2.34, "Not ready": 3.39},
            vent_rate=0.275,
            vasopressor_rate=0.2,
            generated_at="2026-09-08T12:00:00Z",
        )
        assert r.total_census == 40
        assert r.vent_rate == pytest.approx(0.275)

    def test_band_count_percentages(self) -> None:
        b = BandCount(band="Ready", count=13, pct=32.5)
        assert b.pct == pytest.approx(32.5)
