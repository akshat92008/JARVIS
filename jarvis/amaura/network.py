"""Network egress controls shared by agents and production provider adapters."""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from jarvis.amaura.models import GovernanceError

_BLOCKED_HOSTS = {
    "metadata.google.internal",
    "metadata.aws.internal",
    "instance-data",
}


@dataclass(frozen=True, slots=True)
class ValidatedDestination:
    url: str
    scheme: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _address_is_public(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def validate_public_url(
    url: str,
    *,
    resolve: bool = True,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> ValidatedDestination:
    """Validate both the literal URL and every resolved address.

    Resolution occurs immediately before a request. Callers must disable
    redirects so a validated public destination cannot redirect to a private
    or cloud-metadata address.
    """

    try:
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise GovernanceError("Malformed outbound URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise GovernanceError("Only absolute HTTP(S) URLs are allowed")
    if parsed.username or parsed.password:
        raise GovernanceError("URLs containing credentials are not allowed")
    hostname = parsed.hostname.rstrip(".").lower()
    if (
        hostname == "localhost"
        or hostname.endswith((".localhost", ".local", ".internal"))
        or hostname in _BLOCKED_HOSTS
    ):
        raise GovernanceError("Local and metadata-service hosts are blocked")

    addresses: set[str] = set()
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        addresses.add(str(literal))
    elif resolve:
        try:
            records = resolver(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise GovernanceError(
                f"Outbound hostname could not be resolved: {hostname}"
            ) from exc
        for record in records:
            sockaddr = record[4]
            if sockaddr:
                addresses.add(str(sockaddr[0]).split("%", 1)[0])
        if not addresses:
            raise GovernanceError(
                f"Outbound hostname resolved to no usable address: {hostname}"
            )
    if any(not _address_is_public(address) for address in addresses):
        raise GovernanceError(
            "Private, loopback, link-local, reserved, and metadata network "
            "destinations are blocked"
        )
    return ValidatedDestination(
        url=url,
        scheme=parsed.scheme,
        hostname=hostname,
        port=port,
        addresses=tuple(sorted(addresses)),
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise GovernanceError(
            f"Outbound redirects are disabled (provider returned HTTP {code})"
        )


def request_json(
    url: str,
    *,
    method: str = "POST",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
    opener: Any | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    """Send one redirect-free JSON request to a freshly validated destination."""

    validate_public_url(url, resolve=True)
    body = None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "Amaura-Internal-Workforce/1.1",
        **(headers or {}),
    }
    if payload is not None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method.upper(),
    )
    client = opener or urllib.request.build_opener(_NoRedirect())
    try:
        with client.open(request, timeout=max(1.0, min(timeout, 60.0))) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise GovernanceError("Provider response exceeded the 2 MB limit")
            status = int(response.status)
            final_url = response.geturl()
            if final_url != url:
                raise GovernanceError("Provider transport changed destination")
            response_headers = {
                str(key).lower(): str(value) for key, value in response.headers.items()
            }
    except GovernanceError:
        raise
    except urllib.error.HTTPError as exc:
        raise GovernanceError(f"Provider returned HTTP {exc.code}") from exc
    except (OSError, urllib.error.URLError) as exc:
        raise GovernanceError("Provider request failed") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GovernanceError("Provider returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise GovernanceError("Provider response must be a JSON object")
    return status, decoded, response_headers


def fetch_public_text(url: str, *, max_length: int = 10_000) -> str:
    """Fetch public evidence with DNS validation, no redirects, and a size cap."""

    validate_public_url(url, resolve=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Amaura-Evidence-Fetcher/1.1"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            if response.geturl() != url:
                raise GovernanceError("Web fetch changed destination")
            raw = response.read(max(1, min(max_length, 100_000)) + 1)
    except GovernanceError:
        raise
    except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise GovernanceError("Public evidence fetch failed") from exc
    limit = max(1, min(max_length, 100_000))
    if len(raw) > limit:
        raw = raw[:limit]
    return raw.decode("utf-8", errors="replace")


__all__ = [
    "ValidatedDestination",
    "fetch_public_text",
    "request_json",
    "validate_public_url",
]
