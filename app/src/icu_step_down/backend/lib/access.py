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

App-level per-team scoping is a documented follow-up (FUTURE WORK). It would
require either Postgres row security policies on the synced Lakebase tables, or
app-side filtering that applies care_unit restrictions before returning data.

This module provides the mapping helper that a future enforcement layer would
call. It is NOT wired into any live query path yet.
"""

from __future__ import annotations

# Mapping from icu_* group name to the care_unit value it grants access to.
_GROUP_TO_CARE_UNIT: dict[str, str] = {
    "icu_micu": "MICU",
    "icu_sicu": "SICU",
    "icu_ccu": "CCU",
}

_ADMIN_GROUP = "icu_admins"


def care_unit_filter_for_user(groups: list[str]) -> list[str] | None:
    """
    Map a user's icu_* group memberships to the allowed care_unit values.

    Intended for future app-side enforcement of per-care-team scoping on the
    Lakebase query path. NOT currently wired into any live route.

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
