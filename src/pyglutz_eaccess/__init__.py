"""Async client for the Glutz eAccess JSON-RPC API."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .client import (
    GlutzAPI,
    GlutzAuthError,
    GlutzConnectionError,
    parse_invitation,
    resolve_instance_host,
    set_new_password,
)

__all__ = [
    "GlutzAPI",
    "GlutzAuthError",
    "GlutzConnectionError",
    "parse_invitation",
    "resolve_instance_host",
    "set_new_password",
    "__version__",
]

try:
    __version__ = version("pyglutz-eaccess")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"
