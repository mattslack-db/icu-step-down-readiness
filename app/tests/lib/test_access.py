"""
Unit tests for app/src/icu_step_down/backend/lib/access.py.

Tests cover care_unit_filter_for_user: admin path (→ None), single-unit
paths, multi-unit paths, and the fail-closed deny path.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from icu_step_down.backend.lib.access import (
    care_unit_filter_clause,
    care_unit_filter_for_user,
    care_units_from_me,
    scope_denies_all,
)


def _fake_me(*group_displays: str | None) -> SimpleNamespace:
    """Build a duck-typed current_user.me() result with the given group displays."""
    return SimpleNamespace(groups=[SimpleNamespace(display=d) for d in group_displays])


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


# ---------------------------------------------------------------------------
# care_units_from_me — resolve scope from a current_user.me() result
# ---------------------------------------------------------------------------


class TestCareUnitsFromMe:
    def test_admin_group_returns_none(self) -> None:
        assert care_units_from_me(_fake_me("icu_admins")) is None

    def test_single_unit_group_returns_unit(self) -> None:
        assert care_units_from_me(_fake_me("icu_micu")) == ["MICU"]

    def test_no_icu_groups_returns_empty_deny(self) -> None:
        assert care_units_from_me(_fake_me("some_other_group")) == []

    def test_groups_none_returns_empty_deny(self) -> None:
        """me.groups is None (no group claims) → fail-closed deny."""
        assert care_units_from_me(SimpleNamespace(groups=None)) == []

    def test_group_with_no_display_is_ignored(self) -> None:
        """A group whose display is None is skipped, not crashed on."""
        assert care_units_from_me(_fake_me(None, "icu_sicu")) == ["SICU"]

    def test_me_without_groups_attr_returns_empty_deny(self) -> None:
        assert care_units_from_me(SimpleNamespace()) == []


# ---------------------------------------------------------------------------
# scope_denies_all
# ---------------------------------------------------------------------------


class TestScopeDeniesAll:
    def test_none_is_not_deny(self) -> None:
        assert scope_denies_all(None) is False

    def test_empty_list_is_deny(self) -> None:
        assert scope_denies_all([]) is True

    def test_non_empty_list_is_not_deny(self) -> None:
        assert scope_denies_all(["MICU"]) is False


# ---------------------------------------------------------------------------
# care_unit_filter_clause — parameterised SQL predicate
# ---------------------------------------------------------------------------


class TestCareUnitFilterClause:
    def test_none_scope_returns_no_clause(self) -> None:
        fragment, params = care_unit_filter_clause(None)
        assert fragment is None
        assert params == {}

    def test_single_unit_builds_one_placeholder(self) -> None:
        fragment, params = care_unit_filter_clause(["MICU"])
        assert fragment == '"care_unit" IN (:cu_0)'
        assert params == {"cu_0": "MICU"}

    def test_multi_unit_builds_placeholders_in_order(self) -> None:
        fragment, params = care_unit_filter_clause(["MICU", "SICU"])
        assert fragment == '"care_unit" IN (:cu_0, :cu_1)'
        assert params == {"cu_0": "MICU", "cu_1": "SICU"}

    def test_empty_deny_scope_raises(self) -> None:
        """The empty deny list must be short-circuited by the caller, not built."""
        with pytest.raises(ValueError, match="deny-all"):
            care_unit_filter_clause([])

    def test_value_outside_allowlist_raises(self) -> None:
        """Defensive: a care_unit not produced by the mapper is rejected."""
        with pytest.raises(ValueError, match="allowlist"):
            care_unit_filter_clause(["MICU'; DROP TABLE census;--"])

    def test_params_are_bound_not_interpolated(self) -> None:
        """Unit values live in params, never in the fragment string itself."""
        fragment, params = care_unit_filter_clause(["CCU"])
        assert "CCU" not in fragment
        assert params["cu_0"] == "CCU"
