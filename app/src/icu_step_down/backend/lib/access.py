"""
App-level per-care-team access scoping helper.

GOVERNANCE NOTE (see also README.md § Governance and
src/governance/row_level_security.sql):

The Unity Catalog row filter (icu_step_down.gold.rls_care_unit) enforces
per-care-team access for DIRECT UC / SQL-warehouse access to
gold.census and gold.patient_features. The Databricks App reads
Lakebase-synced Postgres copies (mimic_iii.census, mimic_iii.patient_features),
which are NOT governed by the UC row filter. The app service principal
(icu_admins) sees all rows from the synced Postgres tables regardless of
which care-unit group the requesting user belongs to.

App-level per-team scoping is wired into the census, patient-detail, and
analytics read paths via the ``care_unit`` column on ``mimic_iii.census``.
Enforcement is gated by the ``enforce_unit_access`` config flag (env
``<APP_SLUG>_ENFORCE_UNIT_ACCESS``), which defaults to OFF so the existing
deployment's behaviour is unchanged until an operator enables it and verifies
the OBO group resolution live. When ON, the requesting user's icu_* group
memberships (read from the OBO ``current_user.me()`` result) are mapped to the
care_unit values they may see; a user in no recognised group is denied all
rows (fail-closed).

The Unity Catalog row filter (icu_step_down.gold.rls_care_unit) still governs
DIRECT UC / SQL-warehouse access; this module governs the app's Lakebase path,
which the UC filter cannot reach. The two enforce the same care_unit mapping
at different layers.
"""

from __future__ import annotations

from typing import Any

# Mapping from icu_* group name to the care_unit value it grants access to.
_GROUP_TO_CARE_UNIT: dict[str, str] = {
    "icu_micu": "MICU",
    "icu_sicu": "SICU",
    "icu_ccu": "CCU",
}

_ADMIN_GROUP = "icu_admins"

# care_unit values a scope may legitimately contain. A value outside this set is
# a programming error (the mapper only ever produces these), so it is rejected
# defensively before it can be interpolated into a SQL string.
_ALLOWED_CARE_UNITS: frozenset[str] = frozenset(_GROUP_TO_CARE_UNIT.values())


def care_unit_filter_for_user(groups: list[str]) -> list[str] | None:
    """
    Map a user's icu_* group memberships to the allowed care_unit values.

    Wired into the census / patient-detail / analytics read paths via
    :func:`care_units_from_me` and the ``_get_care_unit_scope`` request
    dependency (enforced when the ``enforce_unit_access`` config flag is ON).

    Returns:
        None        — user is in icu_admins; sees all care_units (no filter).
        list[str]   — non-empty list of allowed care_unit strings
                      (e.g. ["MICU"] for icu_micu members).
        []          — user has no recognised icu_* group; deny-all (fail-closed).
                      Callers should treat an empty return as "access denied."

    Args:
        groups: List of group names the requesting user belongs to (e.g. from
                the Databricks Apps X-Forwarded-Groups header or OBO token claims).
    """
    if _ADMIN_GROUP in groups:
        return None  # admin → unrestricted access to all care_units

    allowed: list[str] = []
    for group in groups:
        unit = _GROUP_TO_CARE_UNIT.get(group)
        if unit is not None:
            allowed.append(unit)

    # Empty list → fail-closed: no recognised icu_* group membership → deny all.
    return allowed


def care_units_from_me(me: Any) -> list[str] | None:
    """
    Resolve a care-unit scope from a Databricks ``current_user.me()`` result.

    Extracts group display names from ``me.groups`` (each a ComplexValue with a
    ``.display`` attribute) and maps them via :func:`care_unit_filter_for_user`.

    Returns:
        None       — user is in icu_admins (unrestricted).
        list[str]  — non-empty list of allowed care_unit values.
        []         — no recognised icu_* group (fail-closed deny).

    Duck-typed on purpose (reads ``.groups`` / ``.display``) so it is unit-
    testable without constructing SDK objects.
    """
    raw_groups = getattr(me, "groups", None) or []
    groups = [g.display for g in raw_groups if getattr(g, "display", None)]
    return care_unit_filter_for_user(groups)


def scope_denies_all(scope: list[str] | None) -> bool:
    """
    True when ``scope`` is a fail-closed deny (an empty list).

    None means "admin / unrestricted" and a non-empty list means "restricted to
    these units" — neither denies. Callers short-circuit on a deny (return an
    empty result / 404) before building any SQL.
    """
    return scope is not None and not scope


def care_unit_filter_clause(
    scope: list[str] | None,
) -> tuple[str | None, dict[str, str]]:
    """
    Build a parameterised ``care_unit`` SQL predicate for a scope.

    Returns:
        (None, {})          — scope is None → no restriction (admin).
        (fragment, params)  — scope is a non-empty list → a bound-parameter
                              ``"care_unit" IN (:cu_0, ...)`` predicate and its
                              params, safe to append to a WHERE/AND clause.

    Raises:
        ValueError — scope is the empty deny list (caller must short-circuit via
                     :func:`scope_denies_all` first), or contains a value
                     outside the internal allowlist (defensive; never happens
                     for mapper output).

    Bound parameters (never string interpolation of the unit values) keep the
    predicate injection-safe even though the values are internal constants.
    """
    if scope is None:
        return None, {}
    if not scope:
        raise ValueError(
            "empty scope is deny-all; call scope_denies_all() and short-circuit "
            "before building a SQL clause"
        )
    for unit in scope:
        if unit not in _ALLOWED_CARE_UNITS:
            raise ValueError(f"care_unit {unit!r} is not in the allowlist")
    placeholders = ", ".join(f":cu_{i}" for i in range(len(scope)))
    params = {f"cu_{i}": unit for i, unit in enumerate(scope)}
    return f'"care_unit" IN ({placeholders})', params
