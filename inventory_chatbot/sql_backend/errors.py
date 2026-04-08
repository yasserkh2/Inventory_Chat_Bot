from __future__ import annotations


class SQLBackendConfigurationError(ValueError):
    """Raised when SQL backend configuration is incomplete or invalid."""


class SQLBackendRuntimeError(RuntimeError):
    """Raised when SQL backend runtime operations fail."""

