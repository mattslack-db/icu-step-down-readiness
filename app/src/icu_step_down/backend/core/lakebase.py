"""Lakebase (Databricks Postgres) integration: config, engine, session, and dependency.

Uses the ``ws.postgres`` SDK service (new Lakebase API, not legacy ``ws.database``).
Credentials are refreshed on every new connection via ``generate_database_credential``.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncGenerator, TypeAlias

from databricks.sdk import WorkspaceClient
from fastapi import FastAPI, Request
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, event
from sqlmodel import Session, SQLModel, text

from ._base import LifespanDependency
from ._config import logger


# ---------------------------------------------------------------------------
# Database config
# ---------------------------------------------------------------------------


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    port: int = Field(
        description="Postgres port",
        default=5432,
        validation_alias="PGPORT",
    )
    database_name: str = Field(
        description="Postgres database name to connect to",
        default="databricks_postgres",
        # Databricks Apps injects PGDATABASE; local dev uses DATABASE_NAME.
        validation_alias=AliasChoices("PGDATABASE", "DATABASE_NAME"),
    )
    postgres_endpoint: str = Field(
        description=(
            "Full Lakebase endpoint resource path, e.g. "
            "projects/icu-step-down/branches/production/endpoints/primary"
        ),
        # Databricks Apps injects LAKEBASE_ENDPOINT; local dev uses PGENDPOINT.
        validation_alias=AliasChoices("LAKEBASE_ENDPOINT", "PGENDPOINT"),
    )
    # Platform-injected host (PGHOST); when set, skip the ws.postgres.get_endpoint()
    # API call and use this host directly.
    pg_host: str | None = Field(
        default=None,
        validation_alias="PGHOST",
        description="Postgres host (auto-injected by Databricks Apps postgres resource)",
    )


# ---------------------------------------------------------------------------
# Dev mode helpers
# ---------------------------------------------------------------------------


def _get_dev_db_port() -> int | None:
    """Check for APX_DEV_DB_PORT environment variable for local development.

    Returns None when PGENDPOINT is set — this project connects directly to
    the Lakebase Postgres endpoint and does not use the apx embedded PGLite DB.
    """
    if os.environ.get("PGENDPOINT") or os.environ.get("LAKEBASE_ENDPOINT"):
        # Always use Lakebase when a real endpoint is configured; ignore the
        # embedded PGLite that apx spins up for simpler scaffold projects.
        return None
    port = os.environ.get("APX_DEV_DB_PORT")
    return int(port) if port else None


# ---------------------------------------------------------------------------
# Engine creation
# ---------------------------------------------------------------------------


def _get_host_and_cred(
    db_config: DatabaseConfig, ws: WorkspaceClient
) -> tuple[str, str]:
    """
    Fetch the Lakebase endpoint host and generate a fresh OAuth token.

    When the Databricks Apps platform has injected PGHOST (via the postgres
    resource), uses that directly to avoid the get_endpoint() API call.

    Returns:
        (host, token) tuple.

    Raises:
        RuntimeError if the endpoint or credential cannot be fetched.
    """
    # Fast path: PGHOST injected by the Databricks Apps platform postgres resource
    if db_config.pg_host:
        host = db_config.pg_host
        logger.info("Using platform-injected PGHOST: %s", host)
    else:
        # Resolve host from the endpoint resource (local dev path)
        try:
            endpoint = ws.postgres.get_endpoint(db_config.postgres_endpoint)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to get Lakebase endpoint {db_config.postgres_endpoint!r}: {exc}"
            ) from exc

        # Navigate endpoint.status.hosts.host — accommodate both dict and dataclass
        try:
            status = endpoint.status
            hosts = status.hosts if hasattr(status, "hosts") else {}
            if isinstance(hosts, dict):
                host = hosts.get("host", "")
            else:
                host = getattr(hosts, "host", "")
        except Exception:
            host = ""

        if not host:
            raise RuntimeError(
                f"Lakebase endpoint {db_config.postgres_endpoint!r} returned no host. "
                f"endpoint.status = {getattr(endpoint, 'status', None)}"
            )

    try:
        cred = ws.postgres.generate_database_credential(
            endpoint=db_config.postgres_endpoint
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to generate Lakebase credential for "
            f"{db_config.postgres_endpoint!r}: {exc}"
        ) from exc

    token: str = cred.token or ""
    if not token:
        raise RuntimeError(
            "generate_database_credential returned an empty token."
        )
    return host, token


def _build_engine_url(
    db_config: DatabaseConfig,
    ws: WorkspaceClient,
    dev_port: int | None,
    initial_host: str,
) -> str:
    """Build the SQLAlchemy engine URL."""
    if dev_port:
        password = os.environ.get("APX_DEV_DB_PWD")
        if password is not None:
            logger.info("Using local dev database at localhost:%d", dev_port)
            return (
                f"postgresql+psycopg://postgres:{password}"
                f"@localhost:{dev_port}/{db_config.database_name}?sslmode=disable"
            )
        else:
            raise ValueError(
                "APX_DEV_DB_PORT is set but APX_DEV_DB_PWD is absent. "
                "This project connects directly to Lakebase and does not use "
                "the embedded PGLite database. Either set APX_DEV_DB_PWD for "
                "local PGLite dev, or unset APX_DEV_DB_PORT to connect to "
                "the Lakebase endpoint directly."
            )

    # Production / local-against-sandbox mode
    logger.info("Using Lakebase endpoint: %s", db_config.postgres_endpoint)
    username = (
        ws.config.client_id
        if ws.config.client_id
        else ws.current_user.me().user_name
    )
    return (
        f"postgresql+psycopg://{username}:@{initial_host}"
        f":{db_config.port}/{db_config.database_name}"
    )


def create_db_engine(
    db_config: DatabaseConfig, ws: WorkspaceClient
) -> Engine:
    """
    Create a SQLAlchemy engine connected to the Lakebase instance.

    Production mode: uses a ``creator=`` function that calls
    ``generate_database_credential`` on every new connection to get a
    fresh OAuth token and opens the psycopg3 connection directly.
    This bypasses SQLAlchemy URL-based credential handling entirely.

    Dev mode: connects to the local embedded PGLite database.
    """
    import psycopg as _psycopg  # type: ignore[import]

    dev_port = _get_dev_db_port()

    if dev_port:
        engine_url = _build_engine_url(db_config, ws, dev_port, "")
        engine = create_engine(
            engine_url,
            pool_size=4,
            pool_recycle=45 * 60,
        )
        return engine

    # Production: resolve host once at startup
    initial_host, _ = _get_host_and_cred(db_config, ws)
    # Prefer platform-injected host if available and non-empty
    host = db_config.pg_host or initial_host
    port = db_config.port
    dbname = db_config.database_name
    endpoint = db_config.postgres_endpoint
    # The username is the SP client_id (or user email in local dev).
    # In deployed Databricks Apps, ws.config.client_id is the app SP's client_id UUID.
    username = (
        ws.config.client_id
        if ws.config.client_id
        else ws.current_user.me().user_name
    )
    logger.info("Lakebase engine: host=%s dbname=%s username=%s", host, dbname, username)

    def _creator():
        """Called by SQLAlchemy pool for every new physical connection.

        Generates a fresh Lakebase OAuth token via generate_database_credential
        and opens a direct psycopg3 connection.  This bypasses SQLAlchemy URL
        credential handling entirely, which avoids the cparams override issue
        seen with do_connect + psycopg3 AdaptersMap context.
        """
        try:
            cred = ws.postgres.generate_database_credential(endpoint=endpoint)
            token = cred.token or ""
        except Exception as exc:
            logger.error("Failed to generate Lakebase credential: %s", exc)
            raise RuntimeError(
                f"Failed to generate Lakebase credential: {exc}"
            ) from exc

        if not token:
            raise RuntimeError("generate_database_credential returned empty token.")

        return _psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=username,
            password=token,
            sslmode="require",
        )

    # Use dummy URL so SQLAlchemy knows the dialect; actual connections via creator=
    engine = create_engine(
        "postgresql+psycopg://",
        creator=_creator,
        pool_size=4,
        pool_recycle=45 * 60,
    )
    return engine


def validate_db(engine: Engine, db_config: DatabaseConfig) -> None:
    """Validate that the database connection works by executing SELECT 1."""
    dev_port = _get_dev_db_port()
    target = (
        f"localhost:{dev_port}" if dev_port else db_config.postgres_endpoint
    )
    logger.info("Validating Lakebase connection to %s ...", target)
    try:
        with Session(engine) as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:
        raise ConnectionError(
            f"Failed to connect to Lakebase ({target}): {exc}"
        ) from exc
    logger.info("Lakebase connection validated successfully.")


def initialize_models(engine: Engine) -> None:
    """Create all SQLModel tables (no-op when no SQLModel models are defined)."""
    logger.info("Initializing database models")
    SQLModel.metadata.create_all(engine)
    logger.info("Database models initialized successfully")


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


class _LakebaseDependency(LifespanDependency):
    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncGenerator[None, None]:
        db_config = DatabaseConfig()  # ty: ignore[missing-argument]
        ws = app.state.workspace_client

        engine = create_db_engine(db_config, ws)
        validate_db(engine, db_config)
        initialize_models(engine)

        app.state.engine = engine
        yield
        engine.dispose()

    @staticmethod
    def __call__(request: Request) -> Generator[Session, None, None]:
        with Session(bind=request.app.state.engine) as session:
            yield session


LakebaseDependency: TypeAlias = Annotated[Session, _LakebaseDependency.depends()]
