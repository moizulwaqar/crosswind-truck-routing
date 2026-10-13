"""Shared HTTP session with retries for all third-party calls."""
from __future__ import annotations

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ProviderError(Exception):
    """A third-party API failed or returned something unusable."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.6,
            # 429 is a quota response, not a blip. Retrying it hides the reason
            # and burns the rest of the allowance.
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=16)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers["User-Agent"] = settings.HTTP_USER_AGENT
        _session = s
    return _session


def get_json(url: str, params: dict | None = None, service: str = "API"):
    if settings.FAKE_PROVIDERS:
        from . import fake

        return fake.dispatch(url, params)
    try:
        resp = session().get(url, params=params, timeout=settings.HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ProviderError(f"{service} is unreachable: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        detail = ""
        try:
            body = resp.json()
            detail = body.get("reason") or body.get("message") or ""
        except ValueError:
            pass
        raise ProviderError(f"{service} returned HTTP {resp.status_code} {detail}".strip())
    try:
        return resp.json()
    except ValueError as exc:
        raise ProviderError(f"{service} returned invalid JSON") from exc
