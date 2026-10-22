"""Smoke tests for the enterprise security baseline.

Covers:
  - OWASP security headers on every response (main.py middleware)
  - Rate-limiter client-IP resolution behind the proxy chain (limiter.py)
  - Upload validator size + MIME checks (utils/uploads.py)

NOT covered here (timing-sensitive, run manually if needed):
  - Rate limiter 429 — requires 100+ rapid requests which makes the
    suite slow. To verify: `hey -n 200 -c 10 http://localhost:8080/health`
    and expect some 429s after the 100/min global cap.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile
from limiter import _client_ip
from starlette.datastructures import Headers
from utils.uploads import IMAGE_MIMES, validate_upload


def _make_upload(payload: bytes, content_type: str, filename: str = "f.bin") -> UploadFile:
    """Build an UploadFile with a settable content-type for test cases.

    Starlette's UploadFile.content_type is a read-only property backed by
    self.headers — you can't assign to it, you pass headers at construction.
    """
    return UploadFile(
        filename=filename,
        file=io.BytesIO(payload),
        headers=Headers({"content-type": content_type}),
    )


def test_security_headers_on_health(client):
    """Every response carries the OWASP header set."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "no-referrer"
    assert "Permissions-Policy" in response.headers


def test_csp_on_api_paths_but_not_docs(client):
    """CSP is strict for API responses but relaxed for swagger /api/docs.

    /api/docs is only served when settings.debug is true; in production it
    returns 404 (openapi_url is None). We accept either shape.
    """
    health = client.get("/health")
    assert health.headers.get("Content-Security-Policy", "").startswith("default-src 'none'")

    docs = client.get("/api/docs")
    if docs.status_code == 200:
        assert "Content-Security-Policy" not in docs.headers


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    """Minimal stand-in for Starlette Request — only what _client_ip reads."""

    def __init__(self, headers: dict[str, str], peer: str = "10.0.0.1") -> None:
        self.headers = Headers(headers)
        self.client = _FakeClient(peer)


def test_client_ip_uses_xaio_header_when_no_cloudfront():
    """X-Xaio-Client-IP (injected and overwritten by the subdomain_router
    CloudFront Function, so spoof-proof) is used when CloudFront-Viewer-Address
    is absent — which is the real published-app path, where the
    AllViewerExceptHostHeader origin policy does not forward the CloudFront
    header. It wins over the spoofable X-Forwarded-For and the socket peer."""
    req = _FakeRequest(
        {
            "X-Xaio-Client-IP": "198.51.100.5",
            "X-Forwarded-For": "9.9.9.9",
        },
        peer="10.0.0.1",
    )
    assert _client_ip(req) == "198.51.100.5"


def test_client_ip_prefers_cloudfront_viewer_address():
    """CloudFront-Viewer-Address is used when the XAIO header is absent; :port stripped."""
    req = _FakeRequest({"CloudFront-Viewer-Address": "203.0.113.7:54321"}, peer="10.0.0.1")
    assert _client_ip(req) == "203.0.113.7"


def test_client_ip_cloudfront_ipv6_unwrapped():
    """A bracketed IPv6 viewer address is unwrapped and de-ported."""
    req = _FakeRequest({"CloudFront-Viewer-Address": "[2001:db8::1]:443"})
    assert _client_ip(req) == "2001:db8::1"


def test_client_ip_xff_indexed_from_right_ignores_spoof(monkeypatch):
    """With 2 trusted hops, take parts[-2] — the spoofed left-most is ignored.

    XFF = "<spoofed>, <real client added by CloudFront>, <CF edge added by ALB>".
    """
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    req = _FakeRequest({"X-Forwarded-For": "9.9.9.9, 203.0.113.7, 70.132.0.1"})
    assert _client_ip(req) == "203.0.113.7"


def test_client_ip_falls_back_to_socket_peer(monkeypatch):
    """No CloudFront header and no trusted hops → raw socket peer."""
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    req = _FakeRequest({"X-Forwarded-For": "9.9.9.9"}, peer="10.0.0.1")
    assert _client_ip(req) == "10.0.0.1"


def test_upload_oversize_raises_413():
    """validate_upload rejects files over max_mb with HTTP 413."""
    too_big = b"x" * (2 * 1024 * 1024)  # 2 MB
    file = _make_upload(too_big, "image/png", filename="big.png")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(validate_upload(file, max_mb=1, allowed_mimes=IMAGE_MIMES))

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail["code"] == "PAYLOAD_TOO_LARGE"


def test_upload_wrong_mime_raises_415():
    """validate_upload rejects disallowed content-types with HTTP 415."""
    file = _make_upload(b"MZ...", "application/x-msdownload", filename="malicious.exe")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(validate_upload(file, allowed_mimes=IMAGE_MIMES))

    assert exc_info.value.status_code == 415
    assert exc_info.value.detail["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_ok_returns_bytes():
    """Valid uploads return the raw bytes for downstream use."""
    payload = b"\x89PNG\r\n\x1a\n" + b"0" * 128
    file = _make_upload(payload, "image/png", filename="avatar.png")

    result = asyncio.run(validate_upload(file, max_mb=1, allowed_mimes=IMAGE_MIMES))
    assert result == payload
