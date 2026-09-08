"""
Pytest configuration for integration tests.

Provides the `sandbox_conn` session-scoped fixture that connects to the
icu-sandbox Databricks SQL warehouse.  All integration tests that require
live data receive this fixture.  If the sandbox is unreachable the fixture
calls `pytest.skip` with a clear message so the suite can still run in CI
without credentials.
"""

from __future__ import annotations

import warnings

import pytest

# Databricks SQL warehouse details for the icu-sandbox workspace
_WAREHOUSE_ID = "7cdc2b0c4ec592d8"
_PROFILE = "icu-sandbox"


@pytest.fixture(scope="session")
def sandbox_conn():
    """
    Yield an open databricks.sql connection to the icu-sandbox warehouse.

    Skips the test session if:
    - databricks-sdk or databricks-sql-connector are not installed
    - The icu-sandbox Databricks CLI profile is not configured
    - The sandbox host is unreachable (network / auth error)
    """
    try:
        import databricks.sql as sql  # noqa: PLC0415
        from databricks.sdk import WorkspaceClient  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"databricks packages not installed: {exc}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            ws = WorkspaceClient(profile=_PROFILE)
            host = ws.config.host.replace("https://", "")
            http_path = f"/sql/1.0/warehouses/{_WAREHOUSE_ID}"
            token = ws.config.oauth_token().access_token
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"icu-sandbox profile not configured or auth failed: {exc}")

    try:
        conn = sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
        )
        # Smoke-test the connection
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"icu-sandbox SQL warehouse unreachable: {exc}")

    yield conn
    conn.close()
