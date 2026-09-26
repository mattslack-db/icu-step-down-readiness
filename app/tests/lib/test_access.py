"""
Unit tests for app/src/icu_step_down/backend/lib/access.py.

Tests cover care_unit_filter_for_user: admin path (→ None), single-unit
paths, multi-unit paths, and the fail-closed deny path.
"""

from __future__ import annotations

import pytest

from icu_step_down.backend.lib.access import care_unit_filter_for_user


# ---------------------------------------------------------------------------
# Admin path
# ---------------------------------------------------------------------------


class TestAdminAccess:
    def test_admin_returns_none(self) -> None:
        """icu_admins member receives None → no care_unit filter applied."""
        assert care_unit_filter_for_user(["icu_admins"]) is None

    def test_admin_with_additional_unit_groups_still_returns_none(self) -> None:
        """Admin membership supersedes unit-level groups."""
        assert care_unit_filter_for_user(["icu_admins", "icu_micu"]) is None

    def test_admin_with_all_unit_groups_returns_none(self) -> None:
        all_groups = ["icu_admins", "icu_micu", "icu_sicu", "icu_ccu"]
        assert care_unit_filter_for_user(all_groups) is None


# ---------------------------------------------------------------------------
# Single unit paths
# ---------------------------------------------------------------------------


class TestSingleUnitAccess:
    def test_micu_group_returns_micu_list(self) -> None:
        result = care_unit_filter_for_user(["icu_micu"])
        assert result == ["MICU"]

    def test_sicu_group_returns_sicu_list(self) -> None:
        result = care_unit_filter_for_user(["icu_sicu"])
        assert result == ["SICU"]

    def test_ccu_group_returns_ccu_list(self) -> None:
        result = care_unit_filter_for_user(["icu_ccu"])
        assert result == ["CCU"]


# ---------------------------------------------------------------------------
# Multi-unit paths
# ---------------------------------------------------------------------------


class TestMultiUnitAccess:
    def test_micu_and_sicu_returns_both_units(self) -> None:
        result = care_unit_filter_for_user(["icu_micu", "icu_sicu"])
        assert result is not None
        assert sorted(result) == ["MICU", "SICU"]

    def test_all_three_unit_groups_returns_all_units(self) -> None:
        result = care_unit_filter_for_user(["icu_micu", "icu_sicu", "icu_ccu"])
        assert result is not None
        assert sorted(result) == ["CCU", "MICU", "SICU"]


# ---------------------------------------------------------------------------
# Fail-closed deny paths
# ---------------------------------------------------------------------------


class TestDenyAccess:
    def test_empty_groups_returns_empty_list(self) -> None:
        """No groups → fail-closed empty list (deny all)."""
        assert care_unit_filter_for_user([]) == []

    def test_unrecognised_groups_returns_empty_list(self) -> None:
        """Unknown group names → fail-closed empty list (deny all)."""
        result = care_unit_filter_for_user(["some_other_group", "not_an_icu_group"])
        assert result == []

    def test_partial_match_with_unrecognised_returns_only_valid_units(self) -> None:
        """Unknown groups are silently ignored; only valid icu_* groups match."""
        result = care_unit_filter_for_user(["icu_micu", "not_a_real_group"])
        assert result == ["MICU"]


# ---------------------------------------------------------------------------
# Immutability — returned value is a new list
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_returns_new_list_not_input_reference(self) -> None:
        """Returned list for a non-admin user is a new object."""
        groups = ["icu_micu"]
        result = care_unit_filter_for_user(groups)
        assert result is not None
        assert result is not groups

    def test_does_not_mutate_input_groups(self) -> None:
        """Input list is not modified by care_unit_filter_for_user."""
        groups = ["icu_micu", "icu_sicu"]
        original = list(groups)
        care_unit_filter_for_user(groups)
        assert groups == original
