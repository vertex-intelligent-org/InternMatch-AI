"""
Abuse Protection & Rate Limiting Boundary Foundation
Provides atomic, Redis-backed per-authenticated-user fixed-window rate limiting
for expensive backend endpoints. Active only in production environment.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

import redis
from app.core.config import settings
from fastapi import HTTPException, status

RATE_LIMIT_POLICIES: Dict[str, Dict[str, int]] = {
    "cv_upload": {"limit": 5, "window_seconds": 600},
    "compliance_evidence_upload": {"limit": 5, "window_seconds": 600},
    "cv_confirm": {"limit": 10, "window_seconds": 600},
    "avatar_upload": {"limit": 10, "window_seconds": 600},
    "match_calculate": {"limit": 10, "window_seconds": 600},
    "match_explanation": {"limit": 30, "window_seconds": 600},
    "application_generate": {"limit": 10, "window_seconds": 600},
    "interview_prep": {"limit": 10, "window_seconds": 600},
}

_RATE_LIMIT_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


def _get_redis_client() -> redis.Redis:
    """
    Create Redis client with short connection/socket timeout
    for request protection.
    """
    return redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
    )


def enforce_rate_limit(*, user_id: UUID, scope: str) -> None:
    """
    Enforce fixed-window rate limiting for an authenticated user on a specific scope.
    In non-production environments, this is a complete no-op (no Redis calls).
    In production:
    - Atomically increments user-scope counter via Redis Lua script.
    - Raises HTTP 429 if the counter exceeds the policy limit.
    - Fails closed with HTTP 503 if Redis evaluation fails
      (zero credential/exception leakage).
    """
    if scope not in RATE_LIMIT_POLICIES:
        raise ValueError(f"Unknown rate limit scope: '{scope}'")

    if not isinstance(user_id, UUID):
        raise ValueError("user_id must be a valid UUID")

    env = (settings.ENVIRONMENT or "").strip().lower()
    if env != "production":
        return

    policy = RATE_LIMIT_POLICIES[scope]
    limit = policy["limit"]
    window_seconds = policy["window_seconds"]
    redis_key = f"internmatch:rate-limit:{scope}:{user_id}"

    try:
        client = _get_redis_client()
        res: Any = client.eval(_RATE_LIMIT_LUA, 1, redis_key, window_seconds)
        current = int(res[0])
        ttl = int(res[1])
    except HTTPException:
        raise
    except Exception:
        now_iso = datetime.now(timezone.utc).isoformat()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Request protection service is temporarily unavailable.",
                    "details": None,
                    "timestamp": now_iso,
                }
            },
        )

    if current > limit:
        retry_after = max(1, ttl if ttl > 0 else window_seconds)
        now_iso = datetime.now(timezone.utc).isoformat()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many requests. Please retry later.",
                    "details": {
                        "retry_after_seconds": retry_after,
                    },
                    "timestamp": now_iso,
                }
            },
            headers={"Retry-After": str(retry_after)},
        )
