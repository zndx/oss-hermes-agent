"""HTTP dashboard /listen must send the browser to the HTTPS AgentRTC join URL."""
from __future__ import annotations

from starlette.requests import Request

from hermes_cli.web_server_dashboard import listen_http_redirect_url, listen_https_url


def _req(path: str, *, proto: str | None = None, query: str = "", scheme: str = "http") -> Request:
    headers = []
    if proto:
        headers.append((b"x-forwarded-proto", proto.encode()))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": scheme,
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "headers": headers,
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 9119),
        }
    )


def test_http_listen_redirects_to_join_url(monkeypatch):
    monkeypatch.setenv(
        "HERMES_AGENT_RTC_JOIN_URL",
        "https://tinybox.dev.vista.zndx.org:9120/listen",
    )
    dest = listen_http_redirect_url(_req("/listen", query="agenda=note"))
    assert dest == "https://tinybox.dev.vista.zndx.org:9120/listen?agenda=note"


def test_caddy_https_proxy_does_not_redirect(monkeypatch):
    monkeypatch.setenv(
        "HERMES_AGENT_RTC_JOIN_URL",
        "https://tinybox.dev.vista.zndx.org:9120/listen",
    )
    assert listen_http_redirect_url(_req("/listen", proto="https")) is None


def test_other_paths_are_untouched(monkeypatch):
    monkeypatch.setenv(
        "HERMES_AGENT_RTC_JOIN_URL",
        "https://tinybox.dev.vista.zndx.org:9120/listen",
    )
    assert listen_http_redirect_url(_req("/chat")) is None
    assert listen_https_url().startswith("https://")
