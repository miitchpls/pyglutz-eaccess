from __future__ import annotations

import base64
import logging
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)

RPC_TIMEOUT = aiohttp.ClientTimeout(total=10)
_AUTH_ERROR_TOKENS = ("unauthor", "forbidden", "permission denied", "invalid credentials")


class GlutzAuthError(Exception):
    """Raised when authentication fails (invalid credentials)."""


class GlutzConnectionError(Exception):
    """Raised when the API is unreachable or returns an unexpected response."""


def _raise_rpc_error(method: str, error: Any) -> None:
    """Raise GlutzAuthError or GlutzConnectionError based on a JSON-RPC error payload."""
    if isinstance(error, dict):
        message = str(error.get("message") or error)
    else:
        message = str(error)
    if any(token in message.lower() for token in _AUTH_ERROR_TOKENS):
        raise GlutzAuthError(f"{method}: {message}")
    raise GlutzConnectionError(f"{method}: {message}")


def parse_invitation(url: str) -> dict[str, str]:
    """Parse a Glutz eAccess invitation URL into its components.

    Accepts both the web and mobile deep-link formats:
        https://eaccess.ac.glutz.com/invite///cloud.eaccess.glutz.com/building-name
            ?systemid=XXXX&email=user%40example.com&token=XXXXX
        eaccessmobile://cloud.eaccess.glutz.com/building-name
            ?systemid=XXXX&email=user%40example.com&token=XXXXX
    """
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    try:
        email = query["email"][0]
        token = query["token"][0]
    except (KeyError, IndexError) as err:
        raise ValueError("Missing email or token") from err

    if parsed.scheme == "eaccessmobile":
        cloud_host = parsed.netloc
        system_path = parsed.path.lstrip("/")
    else:
        prefix = "/invite/"
        if not parsed.path.startswith(prefix):
            raise ValueError("Missing /invite/ prefix")
        remainder = parsed.path[len(prefix):].lstrip("/")
        parts = remainder.split("/", 1)
        if len(parts) != 2:
            raise ValueError("Missing cloud host or system path")
        cloud_host, system_path = parts

    if not cloud_host or not system_path:
        raise ValueError("Missing cloud host or system path")

    result = {
        "cloud_host": cloud_host,
        "system_path": system_path,
        "email": email,
        "token": token,
    }
    system_id = query.get("systemid", [None])[0]
    if system_id:
        result["system_id"] = system_id
    return result


async def resolve_instance_host(
    session: aiohttp.ClientSession, cloud_host: str, system_path: str
) -> str:
    url = f"https://{cloud_host}/{system_path}"
    try:
        async with session.get(
            url,
            allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status in (301, 302, 307, 308):
                resolved = urlparse(resp.headers.get("Location", "")).hostname
                if isinstance(resolved, str) and resolved:
                    return resolved
    except aiohttp.ClientError as err:
        raise GlutzConnectionError(f"Could not resolve instance host from {url}: {err}") from err

    return cloud_host


async def set_new_password(
    session: aiohttp.ClientSession, host: str, token: str, password: str
) -> None:
    url = f"https://{host}/api/unauthorized/setnewpassword"
    try:
        async with session.post(
            url,
            json={"token": token, "password": password},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 401:
                raise GlutzAuthError("Invalid or expired invitation token")
            resp.raise_for_status()
    except aiohttp.ClientError as err:
        raise GlutzConnectionError(f"Could not set new password at {url}: {err}") from err


class GlutzAPI:
    """Client for the Glutz eAccess JSON-RPC API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        language: str = "en",
    ) -> None:
        self._session = session
        self._url = f"{host}/rpc/"
        self._rpc_id = 0
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {token}",
            "Accept": "*/*",
            "Accept-Language": language,
        }

    async def _rpc(self, method: str, params: list[Any]) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request and return the result payload."""
        self._rpc_id += 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._rpc_id,
        }
        try:
            async with self._session.post(
                self._url,
                json=payload,
                headers=self._headers,
                timeout=RPC_TIMEOUT,
            ) as resp:
                _LOGGER.debug("RPC %s returned HTTP %s", method, resp.status)
                if resp.status == 401:
                    raise GlutzAuthError("Invalid credentials")
                resp.raise_for_status()
                data: dict[str, Any] = await resp.json()
                if "error" in data:
                    _raise_rpc_error(method, data["error"])
                if "result" not in data:
                    raise GlutzConnectionError(f"{method}: missing 'result' in response")
                return cast(dict[str, Any], data["result"])
        except aiohttp.ClientError as err:
            raise GlutzConnectionError(str(err)) from err

    async def get_access_points(self) -> list[dict[str, Any]]:
        """Return all access points available to the authenticated user."""
        result = await self._rpc("eAccess.getAccessPointsRelatedToLoggedInUser", [])
        if not isinstance(result, dict):
            raise GlutzConnectionError(
                "Unexpected getAccessPointsRelatedToLoggedInUser response"
            )
        access_points = result.get("accessPoints")
        if not isinstance(access_points, list):
            raise GlutzConnectionError(
                "Missing 'accessPoints' in getAccessPointsRelatedToLoggedInUser response"
            )
        return cast(list[dict[str, Any]], access_points)

    async def get_system_info(self) -> dict[str, str]:
        """Return the system info (id, name) for the logged-in user's instance.

        The systemid uniquely identifies a Glutz eAccess installation and is
        stable across credential/host changes — used as the ConfigEntry unique_id.
        """
        result = await self._rpc("eAccess.getSystemInfoOfLoggedInUser", [])
        if not isinstance(result, dict):
            raise GlutzConnectionError("Unexpected getSystemInfoOfLoggedInUser response")
        info: dict[str, str] = {}
        system_id = result.get("systemid")
        if isinstance(system_id, str) and system_id:
            info["id"] = system_id
        name = result.get("name")
        if isinstance(name, str) and name:
            info["name"] = name
        return info

    async def open_access_point(self, access_point_id: str) -> bool:
        """Open an access point for 3 seconds (action 2, hardware auto-relock)."""
        result = await self._rpc(
            "eAccess.executeAccessPointAsLoggedInUser",
            [access_point_id, 2],
        )
        status = result.get("status") if isinstance(result, dict) else None
        _LOGGER.debug("open_access_point(%s) -> %s", access_point_id, status)
        return status == "success"

    async def close_access_point(self, access_point_id: str) -> bool:
        """Force-lock an access point using action 16."""
        result = await self._rpc(
            "eAccess.executeAccessPointAsLoggedInUser",
            [access_point_id, 16],
        )
        status = result.get("status") if isinstance(result, dict) else None
        _LOGGER.debug("close_access_point(%s) -> %s", access_point_id, status)
        return status == "success"
