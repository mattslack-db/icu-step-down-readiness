"""
Request dependency that resolves the requesting user's care-unit scope.

Returns a value consumed by the census / patient-detail / analytics routes:
    None       — unrestricted (enforcement OFF, or the user is an icu_admin).
    list[str]  — restricted to these care_unit values.
    []         — fail-closed deny (enforcement ON but the user is in no
                 recognised icu_* group, or their groups could not be resolved).

See lib/access.py and src/governance/row_level_security.sql for the governance
model this enforces on the app's Lakebase path.
"""

from __future__ import annotations

from typing import Annotated, TypeAlias

from databricks.sdk import WorkspaceClient
from fastapi import Depends

from ..lib.access import care_units_from_me
from ._config import logger
from ._defaults import ConfigDependency
from ._headers import HeadersDependency


def _get_care_unit_scope(
    config: ConfigDependency,
    headers: HeadersDependency,
) -> list[str] | None:
    """Resolve the care-unit scope for the current request (fail-closed)."""
    if not config.enforce_unit_access:
        return None  # enforcement disabled → unrestricted (unchanged behaviour)

    if not headers.token:
        logger.warning(
            "Unit-access enforcement is ON but no OBO token (X-Forwarded-Access-"
            "Token) was forwarded; denying all rows (fail-closed)."
        )
        return []

    try:
        user_ws = WorkspaceClient(
            token=headers.token.get_secret_value(), auth_type="pat"
        )
        me = user_ws.current_user.me()
        return care_units_from_me(me)
    except Exception as exc:  # noqa: BLE001 — any failure must fail closed
        logger.error(
            "Care-unit group resolution failed; denying all rows (fail-closed): %s",
            exc,
        )
        return []


CareUnitScopeDependency: TypeAlias = Annotated[
    list[str] | None, Depends(_get_care_unit_scope)
]
