from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from pyglutz_eaccess import (
    GlutzAPI,
    GlutzAuthError,
    GlutzConnectionError,
    parse_invitation,
    resolve_instance_host,
    set_new_password,
)

INVITE_URL = (
    "https://eaccess.ac.glutz.com/invite///cloud.eaccess.glutz.com/building-name"
    "?systemid=SYS123&email=user%40example.com&token=TOK123"
)


def _mock_get_session(status: int, headers: dict | None = None, client_error: Exception | None = None):
    """Return a mock aiohttp.ClientSession that responds to GET with the given status/headers."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.headers = headers or {}
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    if client_error:
        mock_session.get = MagicMock(side_effect=client_error)
    else:
        mock_session.get = MagicMock(return_value=mock_resp)
    return mock_session


def _mock_post_session(status: int, json_body: dict | None = None, client_error: Exception | None = None):
    """Return a mock aiohttp.ClientSession that responds to POST with the given status/body."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_body or {})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    if client_error:
        mock_session.post = MagicMock(side_effect=client_error)
    else:
        mock_session.post = MagicMock(return_value=mock_resp)
    return mock_session


class TestGlutzAPIInit:
    def test_authorization_header(self):
        api = GlutzAPI(MagicMock(), "https://example.com", "user", "secret")
        expected = "Basic " + base64.b64encode(b"user:secret").decode()
        assert api._headers["Authorization"] == expected

    def test_default_language_is_en(self):
        api = GlutzAPI(MagicMock(), "https://example.com", "user", "pass")
        assert api._headers["Accept-Language"] == "en"

    def test_custom_language(self):
        api = GlutzAPI(MagicMock(), "https://example.com", "user", "pass", language="it")
        assert api._headers["Accept-Language"] == "it"

    def test_url_built_from_host(self):
        api = GlutzAPI(MagicMock(), "https://example.com", "user", "pass")
        assert api._url == "https://example.com/rpc/"


class TestGlutzAPIRpc:
    async def test_success_returns_result(self):
        session = _mock_post_session(200, json_body={"result": {"foo": "bar"}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        result = await api._rpc("some.method", [])
        assert result == {"foo": "bar"}

    async def test_401_raises_auth_error(self):
        session = _mock_post_session(401, json_body={})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        with pytest.raises(GlutzAuthError):
            await api._rpc("some.method", [])

    async def test_error_field_raises_connection_error(self):
        session = _mock_post_session(200, json_body={"error": {"code": -1, "message": "fail"}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        with pytest.raises(GlutzConnectionError):
            await api._rpc("some.method", [])

    async def test_network_error_raises_connection_error(self):
        session = _mock_post_session(200, client_error=aiohttp.ClientConnectorError(MagicMock(), OSError()))
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        with pytest.raises(GlutzConnectionError):
            await api._rpc("some.method", [])

    async def test_missing_result_raises_connection_error(self):
        session = _mock_post_session(200, json_body={})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        with pytest.raises(GlutzConnectionError):
            await api._rpc("some.method", [])

    async def test_error_with_auth_message_raises_auth_error(self):
        session = _mock_post_session(
            200, json_body={"error": {"code": -32000, "message": "Unauthorized access"}}
        )
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        with pytest.raises(GlutzAuthError):
            await api._rpc("some.method", [])

    async def test_rpc_id_increments_across_calls(self):
        session = _mock_post_session(200, json_body={"result": {}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        await api._rpc("m1", [])
        await api._rpc("m2", [])
        calls = session.post.call_args_list
        assert calls[0][1]["json"]["id"] == 1
        assert calls[1][1]["json"]["id"] == 2

    async def test_rpc_passes_timeout(self):
        session = _mock_post_session(200, json_body={"result": {}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        await api._rpc("m", [])
        assert session.post.call_args[1]["timeout"] is not None


class TestGlutzAPIMethods:
    async def test_get_access_points_returns_list(self):
        aps = [{"accessPointId": "ap-1"}, {"accessPointId": "ap-2"}]
        session = _mock_post_session(200, json_body={"result": {"accessPoints": aps}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        result = await api.get_access_points()
        assert result == aps

    async def test_get_access_points_raises_when_accesspoints_missing(self):
        session = _mock_post_session(200, json_body={"result": {}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        with pytest.raises(GlutzConnectionError):
            await api.get_access_points()

    async def test_open_access_point_sends_action_2(self):
        session = _mock_post_session(200, json_body={"result": {"status": "success"}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        result = await api.open_access_point("ap-1")
        assert result is True
        payload = session.post.call_args[1]["json"]
        assert payload["params"] == ["ap-1", 2]

    async def test_open_access_point_returns_false_on_non_success(self):
        session = _mock_post_session(200, json_body={"result": {"status": "error"}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        result = await api.open_access_point("ap-1")
        assert result is False

    async def test_close_access_point_sends_action_16(self):
        session = _mock_post_session(200, json_body={"result": {"status": "success"}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        result = await api.close_access_point("ap-1")
        assert result is True
        payload = session.post.call_args[1]["json"]
        assert payload["params"] == ["ap-1", 16]

    async def test_close_access_point_returns_false_on_non_success(self):
        session = _mock_post_session(200, json_body={"result": {"status": "error"}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        result = await api.close_access_point("ap-1")
        assert result is False

    async def test_get_system_info_returns_id_and_name(self):
        session = _mock_post_session(
            200, json_body={"result": {"name": "Palazzo Rossi", "systemid": "SYS1"}}
        )
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        result = await api.get_system_info()
        assert result == {"id": "SYS1", "name": "Palazzo Rossi"}
        payload = session.post.call_args[1]["json"]
        assert payload["method"] == "eAccess.getSystemInfoOfLoggedInUser"
        assert payload["params"] == []

    async def test_get_system_info_omits_missing_name(self):
        session = _mock_post_session(200, json_body={"result": {"systemid": "SYS1"}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        result = await api.get_system_info()
        assert result == {"id": "SYS1"}

    async def test_get_system_info_omits_missing_id(self):
        session = _mock_post_session(200, json_body={"result": {"name": "Palazzo Rossi"}})
        api = GlutzAPI(session, "https://example.com", "user", "pass")
        result = await api.get_system_info()
        assert result == {"name": "Palazzo Rossi"}


class TestParseInvitation:
    def test_valid_url(self):
        result = parse_invitation(INVITE_URL)
        assert result == {
            "cloud_host": "cloud.eaccess.glutz.com",
            "system_path": "building-name",
            "email": "user@example.com",
            "token": "TOK123",
            "system_id": "SYS123",
        }

    def test_mobile_deep_link(self):
        result = parse_invitation(
            "eaccessmobile://cloud.eaccess.glutz.com/lugano-parco-brentani"
            "?systemid=5951.4109&email=user%40example.com&token=TOK123"
        )
        assert result == {
            "cloud_host": "cloud.eaccess.glutz.com",
            "system_path": "lugano-parco-brentani",
            "email": "user@example.com",
            "token": "TOK123",
            "system_id": "5951.4109",
        }

    def test_missing_systemid_is_optional(self):
        result = parse_invitation(
            "https://eaccess.ac.glutz.com/invite///cloud.example.com/bar"
            "?email=a%40b.com&token=T"
        )
        assert "system_id" not in result

    def test_missing_invite_prefix(self):
        with pytest.raises(ValueError):
            parse_invitation("https://eaccess.ac.glutz.com/foo/cloud.example.com/bar?email=a&token=b")

    def test_missing_token(self):
        with pytest.raises(ValueError):
            parse_invitation("https://eaccess.ac.glutz.com/invite///cloud.example.com/bar?email=a")

    def test_missing_email(self):
        with pytest.raises(ValueError):
            parse_invitation("https://eaccess.ac.glutz.com/invite///cloud.example.com/bar?token=b")

    def test_missing_system_path(self):
        with pytest.raises(ValueError):
            parse_invitation("https://eaccess.ac.glutz.com/invite///cloud.example.com?email=a&token=b")


class TestResolveInstanceHost:
    async def test_redirect_returns_location_hostname(self):
        session = _mock_get_session(302, headers={"Location": "https://instance.example.com/foo"})
        result = await resolve_instance_host(session, "cloud.example.com", "building")
        assert result == "instance.example.com"

    async def test_redirect_without_hostname_falls_back(self):
        session = _mock_get_session(302, headers={"Location": ""})
        result = await resolve_instance_host(session, "cloud.example.com", "building")
        assert result == "cloud.example.com"

    async def test_non_redirect_returns_cloud_host(self):
        session = _mock_get_session(200)
        result = await resolve_instance_host(session, "cloud.example.com", "building")
        assert result == "cloud.example.com"

    async def test_client_error_raises_connection_error(self):
        session = _mock_get_session(200, client_error=aiohttp.ClientConnectorError(MagicMock(), OSError()))
        with pytest.raises(GlutzConnectionError):
            await resolve_instance_host(session, "cloud.example.com", "building")


class TestSetNewPassword:
    async def test_success_returns_none(self):
        session = _mock_post_session(200, json_body={})
        result = await set_new_password(session, "host.example.com", "tok", "Secret1!")
        assert result is None

    async def test_401_raises_auth_error(self):
        session = _mock_post_session(401)
        with pytest.raises(GlutzAuthError):
            await set_new_password(session, "host.example.com", "tok", "Secret1!")

    async def test_500_raises_connection_error(self):
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(MagicMock(), (), status=500)
        )
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=mock_resp)
        with pytest.raises(GlutzConnectionError):
            await set_new_password(session, "host.example.com", "tok", "Secret1!")

    async def test_network_error_raises_connection_error(self):
        session = _mock_post_session(200, client_error=aiohttp.ClientConnectorError(MagicMock(), OSError()))
        with pytest.raises(GlutzConnectionError):
            await set_new_password(session, "host.example.com", "tok", "Secret1!")

    async def test_sends_expected_payload(self):
        session = _mock_post_session(200, json_body={})
        await set_new_password(session, "host.example.com", "tok", "Secret1!")
        call_kwargs = session.post.call_args
        assert call_kwargs[0][0] == "https://host.example.com/api/unauthorized/setnewpassword"
        assert call_kwargs[1]["json"] == {"token": "tok", "password": "Secret1!"}
