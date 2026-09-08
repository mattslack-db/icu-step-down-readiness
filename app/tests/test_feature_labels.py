"""
Unit tests for feature label mapping and clinical direction correction.
"""

import pytest

from icu_step_down.backend.lib.feature_labels import (
    ALWAYS_RISK_FEATURES,
    FEATURE_LABELS,
    normalize_factor,
)


class TestFeatureLabels:
    def test_all_30_feature_cols_covered(self) -> None:
        """All 30 model feature columns must have explicit labels."""
        FEATURE_COLS = [
            "hr_mean", "hr_min", "hr_max", "hr_last",
            "sbp_mean", "sbp_min", "sbp_max", "sbp_last",
            "dbp_mean", "dbp_min", "dbp_max", "dbp_last",
            "spo2_mean", "spo2_min", "spo2_max", "spo2_last",
            "temp_c_mean", "temp_c_min", "temp_c_max", "temp_c_last",
            "rr_mean", "rr_min", "rr_max", "rr_last",
            "on_vasopressors", "on_ventilator",
            "gcs_last", "lactate_last", "los", "age",
        ]
        missing = [c for c in FEATURE_COLS if c not in FEATURE_LABELS]
        assert not missing, f"Missing labels for: {missing}"

    def test_labels_are_non_empty_strings(self) -> None:
        for key, label in FEATURE_LABELS.items():
            assert isinstance(label, str) and label, f"Empty label for {key!r}"

    def test_always_risk_features_are_subset_of_feature_labels(self) -> None:
        for feat in ALWAYS_RISK_FEATURES:
            assert feat in FEATURE_LABELS, (
                f"ALWAYS_RISK_FEATURE {feat!r} not in FEATURE_LABELS"
            )


class TestNormalizeFactor:
    def test_on_vasopressors_is_always_risk(self) -> None:
        label, direction, magnitude = normalize_factor("on_vasopressors", "supports", 0.5)
        assert direction == "risk", "on_vasopressors must always be 'risk'"
        assert label == "on vasopressors"

    def test_on_ventilator_is_always_risk(self) -> None:
        label, direction, magnitude = normalize_factor("on_ventilator", "supports", 0.3)
        assert direction == "risk"
        assert label == "on ventilator"

    def test_on_vasopressors_direction_not_overridden_when_already_risk(self) -> None:
        _, direction, _ = normalize_factor("on_vasopressors", "risk", 0.4)
        assert direction == "risk"

    def test_normal_feature_direction_preserved(self) -> None:
        _, direction, _ = normalize_factor("spo2_min", "supports", 0.2)
        assert direction == "supports"

    def test_normal_feature_risk_direction_preserved(self) -> None:
        _, direction, _ = normalize_factor("lactate_last", "risk", 0.24)
        assert direction == "risk"

    def test_known_label_returned(self) -> None:
        label, _, _ = normalize_factor("spo2_min", "supports", 0.1)
        assert label == "minimum SpO₂"

    def test_unknown_feature_falls_back_to_humanized_name(self) -> None:
        label, direction, magnitude = normalize_factor("some_unknown_feat", "supports", 0.1)
        assert label == "some unknown feat"
        assert direction == "supports"
        assert magnitude == 0.1

    def test_magnitude_is_preserved(self) -> None:
        _, _, mag = normalize_factor("gcs_last", "supports", 0.029)
        assert mag == pytest.approx(0.029)

    @pytest.mark.parametrize(
        "raw_name, expected_label",
        [
            ("gcs_last", "GCS (last)"),
            ("lactate_last", "last lactate"),
            ("los", "ICU length of stay (days)"),
            ("age", "age (years)"),
            ("hr_mean", "mean heart rate"),
        ],
    )
    def test_key_clinical_labels(self, raw_name: str, expected_label: str) -> None:
        label, _, _ = normalize_factor(raw_name, "supports", 0.1)
        assert label == expected_label
