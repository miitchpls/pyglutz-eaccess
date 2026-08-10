# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.3] - 2026-08-11
### Fixed
- Catch `TimeoutError` alongside `aiohttp.ClientError` in `resolve_instance_host`,
  `set_new_password` and the RPC client, so an unresponsive host raises
  `GlutzConnectionError` instead of an unhandled timeout.
- Raise `GlutzConnectionError` instead of crashing on malformed JSON bodies,
  non-object JSON responses, and non-object `result` payloads in
  `executeAccessPointAsLoggedInUser`.

## [0.1.0] - 2026-04-19
### Added
- Initial release extracted from the `hass-glutz-eaccess` Home Assistant integration.
- `GlutzAPI` JSON-RPC client.
- `parse_invitation`, `resolve_instance_host`, `set_new_password` helpers.
- `GlutzAuthError`, `GlutzConnectionError` exception types.
