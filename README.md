# pyglutz-eaccess

Async Python client for the [Glutz eAccess](https://www.glutz.com/) cloud-based access control JSON-RPC API.

This library powers the [hass-glutz-eaccess](https://github.com/miitchpls/hass-glutz-eaccess) Home Assistant integration and is published independently for reuse.

## Installation

```bash
pip install pyglutz-eaccess
```

## Usage

```python
import aiohttp
from pyglutz_eaccess import GlutzAPI

async def main():
    async with aiohttp.ClientSession() as session:
        api = GlutzAPI(session, "https://instance.eaccess.glutz.com", "user@example.com", "password")
        points = await api.get_access_points()
        print(points)
```

## Exported API

- `GlutzAPI` — JSON-RPC client (`get_access_points`, `get_system_info`, `open_access_point`, `close_access_point`).
- `GlutzAuthError`, `GlutzConnectionError` — error types.
- `parse_invitation(url)` — parse web/mobile invitation URLs.
- `resolve_instance_host(session, cloud_host, system_path)` — follow the cloud redirect to find the instance host.
- `set_new_password(session, host, token, password)` — activate an account via invitation token.

## License

MIT
