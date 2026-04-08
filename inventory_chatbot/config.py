from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Mapping

from pydantic import BaseModel, Field

DEFAULT_CONFIG_FILE = Path("config.yml")
DEFAULT_ENV_FILE = Path(".env")


class ConfigurationError(ValueError):
    """Raised when provider configuration is incomplete."""


def _strip_optional_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise ConfigurationError(
                f"Invalid .env entry on line {line_number}: expected KEY=VALUE"
            )
        key, value = line.split("=", 1)
        values[key.strip()] = _strip_optional_quotes(value)
    return values


def _load_simple_yaml(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw_line[:1].isspace():
            raise ConfigurationError(
                f"Unsupported indentation in config.yml on line {line_number}. "
                "Use top-level key: value pairs only."
            )
        if ":" not in raw_line:
            raise ConfigurationError(
                f"Invalid config.yml entry on line {line_number}: expected key: value"
            )
        key, value = raw_line.split(":", 1)
        values[key.strip()] = _strip_optional_quotes(value)
    return values


def _lookup(
    source: Mapping[str, str], env_name: str, field_name: str, default: str | None = None
) -> str | None:
    if env_name in source:
        return source[env_name]
    if field_name in source:
        return source[field_name]
    return default


def _parse_int(name: str, raw_value: str) -> int:
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc


def _parse_bool(name: str, raw_value: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean (true/false)")


class AppConfig(BaseModel):
    data_backend: Literal["memory", "sqlserver", "sqlite"] = "memory"
    provider: Literal["openai", "azure"] = "azure"
    openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    model_name: str = "gpt-4.1-mini"
    host: str = "0.0.0.0"
    port: int = 8000
    request_timeout_seconds: int = Field(default=20, ge=1, le=120)
    sqlserver_host: str | None = None
    sqlserver_port: int = 1433
    sqlserver_database: str | None = None
    sqlserver_user: str | None = None
    sqlserver_password: str | None = None
    sqlserver_driver: str = "ODBC Driver 18 for SQL Server"
    sqlserver_encrypt: bool = True
    sqlserver_trust_server_certificate: bool = True
    sqlserver_connection_timeout_seconds: int = Field(default=30, ge=1, le=300)
    sqlite_database_path: str = "inventory_chatbot.sqlite3"

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        env_file: str | Path | None = None,
        config_file: str | Path | None = None,
    ) -> "AppConfig":
        source: dict[str, str] = {}

        if config_file is not None:
            source.update(_load_simple_yaml(Path(config_file)))
        elif env is None:
            source.update(_load_simple_yaml(DEFAULT_CONFIG_FILE))

        if env_file is not None:
            source.update(_load_dotenv(Path(env_file)))
        elif env is None:
            source.update(_load_dotenv(DEFAULT_ENV_FILE))

        source.update(dict(env or os.environ))

        raw_port = _lookup(source, "PORT", "port", "8000") or "8000"
        raw_timeout = (
            _lookup(
                source,
                "REQUEST_TIMEOUT_SECONDS",
                "request_timeout_seconds",
                "20",
            )
            or "20"
        )
        raw_sqlserver_port = _lookup(
            source,
            "SQLSERVER_PORT",
            "sqlserver_port",
            "1433",
        ) or "1433"
        raw_sqlserver_encrypt = _lookup(
            source,
            "SQLSERVER_ENCRYPT",
            "sqlserver_encrypt",
            "true",
        ) or "true"
        raw_sqlserver_trust_server_certificate = _lookup(
            source,
            "SQLSERVER_TRUST_SERVER_CERTIFICATE",
            "sqlserver_trust_server_certificate",
            "true",
        ) or "true"
        raw_sqlserver_connection_timeout = _lookup(
            source,
            "SQLSERVER_CONNECTION_TIMEOUT_SECONDS",
            "sqlserver_connection_timeout_seconds",
            "30",
        ) or "30"

        return cls(
            data_backend=_lookup(source, "DATA_BACKEND", "data_backend", "memory"),
            provider=_lookup(source, "PROVIDER", "provider", "azure"),
            openai_api_key=_lookup(source, "OPENAI_API_KEY", "openai_api_key"),
            azure_openai_endpoint=_lookup(
                source, "AZURE_OPENAI_ENDPOINT", "azure_openai_endpoint"
            ),
            azure_openai_api_key=_lookup(
                source, "AZURE_OPENAI_API_KEY", "azure_openai_api_key"
            ),
            azure_openai_deployment=_lookup(
                source, "AZURE_OPENAI_DEPLOYMENT", "azure_openai_deployment"
            ),
            azure_openai_api_version=_lookup(
                source,
                "AZURE_OPENAI_API_VERSION",
                "azure_openai_api_version",
                "2024-10-21",
            ),
            model_name=_lookup(source, "MODEL_NAME", "model_name", "gpt-4.1-mini"),
            host=_lookup(source, "HOST", "host", "0.0.0.0"),
            port=_parse_int("PORT", raw_port),
            request_timeout_seconds=_parse_int(
                "REQUEST_TIMEOUT_SECONDS", raw_timeout
            ),
            sqlserver_host=_lookup(source, "SQLSERVER_HOST", "sqlserver_host"),
            sqlserver_port=_parse_int("SQLSERVER_PORT", raw_sqlserver_port),
            sqlserver_database=_lookup(source, "SQLSERVER_DATABASE", "sqlserver_database"),
            sqlserver_user=_lookup(source, "SQLSERVER_USER", "sqlserver_user"),
            sqlserver_password=_lookup(source, "SQLSERVER_PASSWORD", "sqlserver_password"),
            sqlserver_driver=_lookup(
                source,
                "SQLSERVER_DRIVER",
                "sqlserver_driver",
                "ODBC Driver 18 for SQL Server",
            ),
            sqlserver_encrypt=_parse_bool(
                "SQLSERVER_ENCRYPT",
                raw_sqlserver_encrypt,
            ),
            sqlserver_trust_server_certificate=_parse_bool(
                "SQLSERVER_TRUST_SERVER_CERTIFICATE",
                raw_sqlserver_trust_server_certificate,
            ),
            sqlserver_connection_timeout_seconds=_parse_int(
                "SQLSERVER_CONNECTION_TIMEOUT_SECONDS",
                raw_sqlserver_connection_timeout,
            ),
            sqlite_database_path=_lookup(
                source,
                "SQLITE_DATABASE_PATH",
                "sqlite_database_path",
                "inventory_chatbot.sqlite3",
            )
            or "inventory_chatbot.sqlite3",
        )

    def validate_provider_credentials(self) -> None:
        if self.provider == "openai":
            if not self.openai_api_key:
                raise ConfigurationError(
                    "OPENAI_API_KEY is required when PROVIDER=openai"
                )
            return

        missing = []
        if not self.azure_openai_endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not self.azure_openai_api_key:
            missing.append("AZURE_OPENAI_API_KEY")
        if not self.azure_openai_deployment:
            missing.append("AZURE_OPENAI_DEPLOYMENT")
        if missing:
            raise ConfigurationError(
                "Missing Azure OpenAI configuration: " + ", ".join(missing)
            )

    def validate_sql_backend_configuration(self) -> None:
        if self.data_backend == "sqlserver":
            missing = []
            if not self.sqlserver_host:
                missing.append("SQLSERVER_HOST")
            if not self.sqlserver_database:
                missing.append("SQLSERVER_DATABASE")
            if not self.sqlserver_user:
                missing.append("SQLSERVER_USER")
            if not self.sqlserver_password:
                missing.append("SQLSERVER_PASSWORD")
            if missing:
                raise ConfigurationError(
                    "Missing SQL Server configuration: " + ", ".join(missing)
                )
            return

        if self.data_backend == "sqlite" and not self.sqlite_database_path.strip():
            raise ConfigurationError(
                "SQLITE_DATABASE_PATH is required when DATA_BACKEND=sqlite"
            )
