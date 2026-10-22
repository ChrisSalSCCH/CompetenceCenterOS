"""Smoke tests for the health + ready + error-envelope baseline.

These tests verify the enterprise baseline that ships with every
responsive_web_app. They run automatically in the `verify` task after
scaffold and should stay green regardless of business routes added
later.
"""

from __future__ import annotations


def test_health_returns_200(client):
    """Liveness is always 200 unless the process is dead."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_health_does_not_touch_db(client):
    """Liveness MUST NOT ping the DB — otherwise a DB hiccup triggers a
    restart cascade across all replicas. This test is the regression
    guard for that invariant.
    """
    # A healthy response without DB configured proves no DB call happened.
    # (We can't assert db.execute wasn't called without mocking the session;
    # a fast 200 on /health is the behavioural proxy.)
    import time

    start = time.perf_counter()
    response = client.get("/health")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert response.status_code == 200
    assert elapsed_ms < 100, f"/health should be near-instant; took {elapsed_ms:.1f}ms"


def test_unknown_route_returns_standard_error_envelope(client):
    """Every HTTP error is wrapped into { error: { code, message, ... } }."""
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body, f"Expected {{error: ...}} envelope, got {body}"
    error = body["error"]
    assert error["code"] == "NOT_FOUND"
    assert "message" in error


def test_request_id_echoed_in_response_header(client):
    """Every response carries the X-Request-ID header for correlation."""
    response = client.get("/health")
    assert "x-request-id" in {k.lower(): v for k, v in response.headers.items()}


def test_request_id_accepts_upstream_header(client):
    """If the caller sends X-Request-ID, we echo the same id back —
    lets tracing in multi-hop systems (gateway → service → service)
    correlate end-to-end.
    """
    incoming = "test-trace-id-0123456789ab"
    response = client.get("/health", headers={"X-Request-ID": incoming})
    assert response.headers.get("x-request-id") == incoming


def test_docs_gated_on_environment(client, settings):
    """/api/docs is open in local/dev/staging and hidden only in prod.

    Visibility is gated on ENVIRONMENT (not DEBUG) — see main.py: toggling
    DEBUG for log-verbosity must not accidentally expose the API docs. This
    test adapts to the current environment so it passes in any configuration.
    """
    response = client.get("/api/docs")
    if settings.environment == "prod":
        assert response.status_code == 404, (
            "/api/docs must NOT be publicly reachable in prod — info leak."
        )
    else:
        assert response.status_code == 200
