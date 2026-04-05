"""Rate limiting and visit throttling for the public vitrine page (abuse mitigation)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
# IP -> deque of request timestamps (sliding window)
_ip_hits: dict[str, deque[float]] = defaultdict(deque)
# (visitor_key, shop_id) -> last recorded visit epoch (dedupe DB writes)
_visit_last: dict[tuple[str, int], float] = {}

# Tuned for a single small shop vitrine; adjust if needed.
PUBLIC_VITRINE_MAX_PER_IP_PER_MIN = 45
PUBLIC_VITRINE_WINDOW_SEC = 60
VISIT_DEDUPE_SEC = 90


def client_ip() -> str:
    from flask import has_request_context, request

    if not has_request_context():
        return "0.0.0.0"
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()[:45]
    return (request.remote_addr or "0.0.0.0")[:45]


def public_vitrine_rate_limit_ok() -> bool:
    """Return False if this IP exceeded the sliding-window limit."""
    ip = client_ip()
    now = time.time()
    with _lock:
        q = _ip_hits[ip]
        while q and q[0] < now - PUBLIC_VITRINE_WINDOW_SEC:
            q.popleft()
        if len(q) >= PUBLIC_VITRINE_MAX_PER_IP_PER_MIN:
            return False
        q.append(now)
        return True


def should_persist_vitrine_visit(visitor_key: str, shop_id: int) -> bool:
    """Avoid writing one DB row per rapid reload from the same visitor (best-effort, per process)."""
    if not visitor_key or not shop_id:
        return True
    now = time.time()
    k = (visitor_key[:128], int(shop_id))
    with _lock:
        last = _visit_last.get(k, 0.0)
        if now - last < VISIT_DEDUPE_SEC:
            return False
        _visit_last[k] = now
        if len(_visit_last) > 80_000:
            # Drop stale entries (older than window) in one pass
            cutoff = now - max(VISIT_DEDUPE_SEC * 4, 600)
            for key in list(_visit_last.keys()):
                if _visit_last[key] < cutoff:
                    del _visit_last[key]
        return True


def apply_vitrine_security_headers(response):
    """Conservative headers for a public, personalized page."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "private, no-cache, must-revalidate"
    return response
