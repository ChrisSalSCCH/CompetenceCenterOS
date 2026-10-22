"""Rate-limiter instance shared between main.py and route modules.

Routes import and decorate sensitive endpoints:

    from limiter import limiter

    @router.post("/login")
    @limiter.limit("5/minute")
    async def login(request: Request, ...):
        ...

The global default (set in main.py) already caps anonymous traffic at
100/min per client. Per-route decorators tighten that for login, password
reset, search, LLM calls, or any endpoint worth protecting specifically.

Storage: in-memory for local/dev (fine, single-process). In prod set
`RATE_LIMIT_STORAGE_URI=redis://host:6379/0` so multi-instance deployments
share one counter.

Client IP resolution (IMPORTANT)
--------------------------------
This app runs behind CloudFront → ALB / API Gateway. The TCP peer the
process sees is the *proxy*, not the user — so keying limits on the raw
socket address (slowapi's default `get_remote_address`) collapses every
visitor into one bucket: a single attacker would lock out all users, and
brute-force protection would be meaningless. `_client_ip` below resolves
the real viewer address instead. See env knobs in its docstring.
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _client_ip(request: Request) -> str:
    """Resolve the real client IP behind the CloudFront/ALB proxy chain.

    Resolution order — most-trusted (least spoofable) first:

    1. ``CloudFront-Viewer-Address`` — CloudFront sets this itself and
       overwrites any client-supplied value, so it is NOT spoofable and is
       independent of how many proxy hops sit in front. Format is ``IP:port``
       (IPv6 bracketed: ``[::1]:port``). Preferred whenever present.

    2. ``X-Xaio-Client-IP`` — injected by the XAIO CloudFront Function
       (subdomain_router) from ``event.viewer.ip``. Also CloudFront-set on the
       *.xaio.app / custom-domain path, but — unlike (1) — a request that
       reaches the origin WITHOUT transiting that function (direct-to-origin,
       a publish path that skips subdomain_router) carries no trusted overwrite,
       so a client could forge it and mint a fresh rate-limit bucket per request.
       Trusted only as a secondary signal, after (1).

    3. ``X-Forwarded-For`` indexed from the RIGHT by ``TRUSTED_PROXY_HOPS``
       — the number of trusted proxies that append to the header
       (CloudFront + ALB = 2). We take ``parts[-hops]`` because each trusted
       proxy appends the address it received the connection from; the
       left-most entries are client-supplied and trivially spoofable, so we
       never trust them. Used when (1) and (2) are unavailable.

    4. Socket peer (``get_remote_address``) — correct for local dev / no
       proxy, and the safe fallback if the headers above are absent.
    """
    cf_viewer = request.headers.get("cloudfront-viewer-address")
    if cf_viewer:
        # Strip the trailing ":port"; rsplit keeps IPv6 colons intact, and
        # strip("[]") unwraps a bracketed IPv6 literal.
        return cf_viewer.rsplit(":", 1)[0].strip("[]") or get_remote_address(request)

    xaio_ip = request.headers.get("x-xaio-client-ip")
    if xaio_ip:
        return xaio_ip.strip()

    hops = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))
    if hops > 0:
        parts = [
            p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()
        ]
        if len(parts) >= hops:
            return parts[-hops]

    return get_remote_address(request)


limiter = Limiter(
    key_func=_client_ip,
    default_limits=["600/minute"],  # the SPA refreshes several queries after every change
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
)
