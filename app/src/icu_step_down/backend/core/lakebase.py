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
from pydantic import Field
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
        validation_alias="DATABASE_NAME",
    )
    postgres_endpoint: str = Field(
        description=(
            "Full Lakebase endpoint resource path, e.g. "
            "projects/icu-step-down/branches/production/endpoints/primary"
        ),
        validation_alias="PGENDPOINT",
    )


# ---------------------------------------------------------------------------
# Dev mode helpers
# ---------------------------------------------------------------------------


def _get_dev_db_port() -> int | None:
    """Check for APX_DEV_DB_PORT environment variable for local development."""
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

    Returns:
        (host, token) tuple.

    Raises:
        RuntimeError if the endpoint or credential cannot be fetched.
    """
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
        logger.info("Using local dev database at localhost:%d", dev_port)
        password = os.environ.get("APX_DEV_DB_PWD")
        if password is None:
            raise ValueError(
                "APX server didn't provide a password; check dev server logs."
            )
        return (
            f"postgresql+psycopg://postgres:{password}"
            f"@localhost:{dev_port}/{db_config.database_name}?sslmode=disable"
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

    In production mode:
    - The engine URL contains a dummy empty password.
    - A ``do_connect`` event listener refreshes the OAuth token before
      every new connection is opened, honoring the 1-hour expiry.
    """
    dev_port = _get_dev_db_port()

    # Fetch the initial host (and a throwaway token to verify connectivity).
    initial_host = ""
    if not dev_port:
        initial_host, _ = _get_host_and_cred(db_config, ws)

    engine_url = _build_engine_url(db_config, ws, dev_port, initial_host)

    engine_kwargs: dict[str, Any] = {
        "pool_size": 4,
        "pool_recycle": 45 * 60,
    }

    if not dev_port:
        engine_kwargs["connect_args"] = {"sslmode": "require"}

    engine = create_engine(engine_url, **engine_kwargs)

    if not dev_port:
        # Refresh the credential on every new physical connection.
        # SQLAlchemy fires ``do_connect`` just before psycopg opens the socket.
        @event.listens_for(engine, "do_connect")
        def _before_connect(dialect, conn_rec, cargs, cparams):  # type: ignore[misc]
            try:
                cred = ws.postgres.generate_database_credential(
                    endpoint=db_config.postgres_endpoint
                )
                cparams["password"] = cred.token or ""
            except Exception as exc:
                logger.error("Failed to refresh Lakebase credential: %s", exc)
                raise

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
