from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from inventory_chatbot.config import AppConfig
from inventory_chatbot.sql_backend.errors import (
    SQLBackendConfigurationError,
    SQLBackendRuntimeError,
)


def build_engine(config: AppConfig):
    config.validate_sql_backend_configuration()
    try:
        from sqlalchemy import create_engine
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency presence
        raise SQLBackendConfigurationError(
            "SQLAlchemy is required for SQL backend mode. Install `sqlalchemy`."
        ) from exc

    if config.data_backend == "sqlserver":
        try:
            import pyodbc  # noqa: F401
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency presence
            raise SQLBackendConfigurationError(
                "pyodbc is required for SQL backend mode. Install `pyodbc` in your virtualenv."
            ) from exc
        except ImportError as exc:  # pragma: no cover - host runtime dependency
            raise SQLBackendConfigurationError(
                "pyodbc is installed but its native ODBC runtime is missing. "
                "Install system packages such as `unixodbc` (and SQL Server ODBC Driver 18)."
            ) from exc

    connection_url = build_sqlalchemy_url(config)
    try:
        return create_engine(connection_url, pool_pre_ping=True)
    except ImportError as exc:  # pragma: no cover - host runtime dependency
        raise SQLBackendConfigurationError(
            "Unable to initialize SQLAlchemy ODBC engine due to missing native ODBC libraries. "
            "Install `unixodbc` and SQL Server ODBC Driver 18 for SQL Server mode."
        ) from exc


def build_sqlalchemy_url(config: AppConfig) -> str:
    if config.data_backend == "sqlite":
        database_path = config.sqlite_database_path.strip()
        if database_path == ":memory:":
            return "sqlite:///:memory:"
        resolved = Path(database_path).expanduser().resolve()
        return f"sqlite:///{resolved}"

    username = quote_plus(config.sqlserver_user or "")
    password = quote_plus(config.sqlserver_password or "")
    host = config.sqlserver_host or ""
    port = config.sqlserver_port
    database = quote_plus(config.sqlserver_database or "")
    driver = quote_plus(config.sqlserver_driver)
    encrypt = "yes" if config.sqlserver_encrypt else "no"
    trust = "yes" if config.sqlserver_trust_server_certificate else "no"
    timeout = config.sqlserver_connection_timeout_seconds
    return (
        f"mssql+pyodbc://{username}:{password}@{host}:{port}/{database}"
        f"?driver={driver}&Encrypt={encrypt}&TrustServerCertificate={trust}&Connection+Timeout={timeout}"
    )


def check_health(engine) -> None:
    try:
        from sqlalchemy import text
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency presence
        raise SQLBackendConfigurationError(
            "SQLAlchemy is required for SQL backend mode. Install `sqlalchemy`."
        ) from exc

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on runtime DB
        raise SQLBackendRuntimeError(f"SQL backend health check failed: {exc}") from exc
