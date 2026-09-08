"""
Unit tests for lakebase.py core module.

Covers _build_engine_url misconfiguration guard:
APX_DEV_DB_PORT set but APX_DEV_DB_PWD absent must raise ValueError so the
app fails fast with a clear message rather than producing a malformed URL.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from icu_step_down.backend.core.lakebase import _build_engine_url, DatabaseConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db_config(
    database_name: str = "testdb",
    port: int = 5432,
    postgres_endpoint: str = "projects/test/branches/main/endpoints/primary",
    pg_host: str | None = None,
) -> DatabaseConfig:
    """Construct a DatabaseConfig without touching real env vars."""
    cfg = MagicMock(spec=DatabaseConfig)
    cfg.database_name = database_name
    cfg.port = port
    cfg.postgres_endpoint = postgres_endpoint
    cfg.pg_host = pg_host
    return cfg


def _mock_ws() -> MagicMock:
    """Return a minimal WorkspaceClient mock."""
    ws = MagicMock()
    ws.config.client_id = "fake-client-id"
    return ws


# ---------------------------------------------------------------------------
# _build_engine_url — dev-port misconfiguration guard
# ---------------------------------------------------------------------------


class TestBuildEngineUrl:
    def test_dev_port_with_password_returns_local_url(self) -> None:
        """When both APX_DEV_DB_PORT and APX_DEV_DB_PWD are set, returns a local URL."""
        cfg = _mock_db_config()
        ws = _mock_ws()
        with patch.dict(os.environ, {"APX_DEV_DB_PWD": "secret"}):
            url = _build_engine_url(cfg, ws, dev_port=5433, initial_host="")
        assert "localhost:5433" in url
        assert "secret" in url
        assert "sslmode=disable" in url

    def test_dev_port_without_password_raises_value_error(self) -> None:
        """APX_DEV_DB_PORT set but APX_DEV_DB_PWD absent must raise ValueError.

        Previously this code fell through to the Lakebase URL builder with an
        empty host, producing a malformed URL.  The ValueError makes the
        misconfiguration explicit and prevents silent incorrect behaviour.
        """
        cfg = _mock_db_config()
        ws = _mock_ws()
        # Ensure APX_DEV_DB_PWD is absent
        env = {k: v for k, v in os.environ.items() if k != "APX_DEV_DB_PWD"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="APX_DEV_DB_PWD"):
                _build_engine_url(cfg, ws, dev_port=5433, initial_host="")

    def test_no_dev_port_returns_lakebase_url(self) -> None:
        """When dev_port is None, the production Lakebase URL is returned."""
        cfg = _mock_db_config(pg_host=None)
        ws = _mock_ws()
        url = _build_engine_url(cfg, ws, dev_port=None, initial_host="my-pg-host.example.com")
        assert "my-pg-host.example.com" in url
        assert "fake-client-id" in url
        assert "sslmode=disable" not in url
