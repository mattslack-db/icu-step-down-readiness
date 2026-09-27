"""
Request dependency that resolves the requesting user's care-unit scope.

Returns a value consumed by the census / patient-detail / analytics routes:
    None       — unrestricted (enforcement OFF, or the user is an icu_admin).
    list[str]  — restricted to these care_unit values.
    []          — the user's access was RESOLVED and they belong to no
                  recognised icu_* group → they legitimately see no unit.

Crucially, this dependency distinguishes "user has no unit" (a resolved deny,
returned as []) from "we could not determine access" (missing OBO token or a
group-resolution failure). The latter raises HTTP 503 rather than returning []:
in a clinical dashboard a silent empty census could be misread as "no patients
in my unit," so a transient auth/SCIM failure must surface as an explicit error,
never as empty data. Both outcomes are fail-closed (no rows are exposed).

LIMITATION — direct group membership only: this reads groups from the OBO
``current_user.me()`` SCIM result, which reports only DIRECT group memberships.
A user who holds icu_admins / icu_micu / etc. transitively through a parent
(nested) group will not have it in ``me.groups`` and would be denied. Assign the
icu_* groups directly to users, and verify membership resolution live before
enabling enforcement.

COST — this makes one WorkspaceClient build + ``current_user.me()`` SCIM call
per request on the read hot path (no caching). Acceptable for the current
demo/pilot scale; a short-TTL per-user scope cache is the documented follow-up
before high-traffic use.

See lib/access.py and src/governance/row_level_security.sql for the governance
model this enforces on the app's Lakebase path.
"""

from __future__ import annotations

from typing import Annotated, TypeAlias

from databricks.sdk import WorkspaceClient
from fastapi import Depends, HTTPException

from ..lib.access import care_units_from_me
from ._config import logger
from ._defaults import ConfigDependency
from ._headers import HeadersDependency

# Raised when the requesting user's access CANNOT be determined (missing OBO
# token or a group-resolution failure). Distinct from a resolved "no unit" deny.
_ACCESS_UNDETERMINED_DETAIL = "Could not determine your access permissions."


def _get_care_unit_scope(
    config: ConfigDependency,
    headers: HeadersDependency,
) -> list[str] | None:
    """Resolve the care-unit scope for the current request (fail-closed).

    Raises HTTP 503 when access cannot be determined (see module docstring);
    returns [] only when access was resolved and the user has no recognised unit.
    """
    if not config.enforce_unit_access:
        return None  # enforcement disabled → unrestricted (unchanged behaviour)

    if not headers.token:
        logger.error(
            "Unit-access enforcement is ON but no OBO token (X-Forwarded-Access-"
            "Token) was forwarded; cannot determine access (returning 503)."
        )
        raise HTTPException(status_code=503, detail=_ACCESS_UNDETERMINED_DETAIL)

    try:
        user_ws = WorkspaceClient(
            token=headers.token.get_secret_value(), auth_type="pat"
        )
        me = user_ws.current_user.me()
    except Exception as exc:  # noqa: BLE001 — any failure surfaces as 503, never rows
        logger.error(
            "Care-unit group resolution failed; cannot determine access "
            "(returning 503): %s",
            exc,
        )
        raise HTTPException(
            status_code=503, detail=_ACCESS_UNDETERMINED_DETAIL
        ) from exc

    return care_units_from_me(me)


CareUnitScopeDependency: TypeAlias = Annotated[
    list[str] | None, Depends(_get_care_unit_scope)
]
