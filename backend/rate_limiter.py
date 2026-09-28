"""Reusable Rate Limiting Dependencies and Decorators for FastAPI."""

from collections import defaultdict
from datetime import datetime, timezone
from functools import wraps
import inspect
import logging
import os
from fastapi import HTTPException, Request

log = logging.getLogger("ssk.rate_limiter")


def _is_test_mode() -> bool:
    """Return True if running in a test or dev environment where test headers may override IP/window.
    In production (ENVIRONMENT='production'), test header overrides are strictly ignored.
    """
    env = os.environ.get("ENVIRONMENT", "development").strip().lower()
    if env == "production":
        return False
    return (
        os.environ.get("TESTING") == "1"
        or os.environ.get("RATE_LIMIT_DISABLED") == "1"
        or env in ("test", "testing", "development")
    )


_redis_client = None
_redis_checked = False

def get_redis_client():
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        try:
            import redis
            _redis_client = redis.from_url(redis_url, decode_responses=True, socket_timeout=1.5)
            _redis_client.ping()
            log.info("RateLimiter: connected to Redis at %s", redis_url.split("@")[-1])
        except Exception as e:
            log.warning("RateLimiter: Redis connection failed (%s); falling back to in-memory", e)
            _redis_client = None
    _redis_checked = True
    return _redis_client


class RateLimiter:
    """Sliding-window rate limiter per user/IP with optional Redis backend and bounded in-memory fallback."""

    def __init__(self, max_requests: int, window_seconds: int = 60, name: str = "request"):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name
        self._history: dict = defaultdict(list)
        self.rejected_count: int = 0

    def get_client_key(self, request: Request) -> str:
        # Header override for test isolation (gated to non-production environments)
        if _is_test_mode():
            test_ip = request.headers.get("x-test-rate-limit-client-ip")
            if test_ip:
                return f"test:{test_ip}"
        
        # User state (set by auth middleware or get_current_user if available)
        user = getattr(request.state, "user", None)
        if user and isinstance(user, dict) and "email" in user:
            return f"user:{user['email']}"

        # Try to extract and decode JWT token to identify the user
        try:
            from auth import get_jwt_secret, JWT_ALGORITHM, JWT_ISSUER, JWT_AUDIENCE
            import jwt
            token = request.cookies.get("access_token")
            if not token:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
            if token:
                payload = jwt.decode(
                    token,
                    get_jwt_secret(),
                    algorithms=[JWT_ALGORITHM],
                    issuer=JWT_ISSUER,
                    audience=JWT_AUDIENCE,
                )
                email = payload.get("email")
                if email:
                    return f"user:{email}"
        except Exception:
            pass

        # Client IP fallback with trusted proxy headers (X-Forwarded-For)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    def check(self, request: Request):
        if _is_test_mode() and (os.environ.get("RATE_LIMIT_DISABLED") == "1" or os.environ.get("TESTING") == "1") and not request.headers.get("x-test-rate-limit-client-ip"):
            return
        key = self.get_client_key(request)
        now_ts = datetime.now(timezone.utc).timestamp()
        
        window = self.window_seconds
        if _is_test_mode():
            test_window = request.headers.get("x-test-rate-limit-window")
            if test_window:
                try:
                    window = int(test_window)
                except ValueError:
                    pass

        # Try Redis sliding window if available
        r = get_redis_client()
        if r is not None:
            r_key = f"ratelimit:{self.name}:{key}"
            try:
                pipe = r.pipeline()
                window_start = now_ts - window
                pipe.zremrangebyscore(r_key, 0, window_start)
                pipe.zcard(r_key)
                pipe.zadd(r_key, {str(now_ts): now_ts})
                pipe.expire(r_key, window + 10)
                res = pipe.execute()
                current_count = res[1]
                if current_count >= self.max_requests:
                    self.rejected_count += 1
                    retry_after = max(1, int(window))
                    log.warning("Rate limit exceeded (Redis) for %s key=%s count=%d max=%d",
                                self.name, key, current_count, self.max_requests)
                    raise HTTPException(
                        status_code=429,
                        detail=f"Too many {self.name} requests. Try again in {retry_after} seconds.",
                        headers={"Retry-After": str(retry_after)},
                    )
                return
            except HTTPException:
                raise
            except Exception as e:
                log.warning("Redis rate limit check error (%s), using in-memory", e)

        # In-memory sliding window fallback with bounded capacity
        window_start = now_ts - window
        if len(self._history) > 10000:
            # Bounded capacity pruning: discard keys idle longer than 2 windows
            stale_keys = [k for k, v in self._history.items() if not v or v[-1] < (now_ts - 2 * window)]
            for sk in stale_keys[:2000]:
                self._history.pop(sk, None)

        self._history[key] = [t for t in self._history[key] if t > window_start]

        if len(self._history[key]) >= self.max_requests:
            self.rejected_count += 1
            retry_after = int(window - (now_ts - self._history[key][0]))
            retry_after = max(retry_after, 1)
            time_fmt = f"{retry_after} seconds" if window < 120 else f"{max(1, retry_after // 60)} minutes"
            
            log.warning("Rate limit exceeded for %s key=%s (limit %d/%ds)",
                        self.name, key, self.max_requests, window)
            
            raise HTTPException(
                status_code=429,
                detail=f"Too many {self.name} requests. Try again in {time_fmt}.",
                headers={"Retry-After": str(retry_after)},
            )

        self._history[key].append(now_ts)

    def reset(self, request: Request):
        key = self.get_client_key(request)
        self._history.pop(key, None)
        r = get_redis_client()
        if r is not None:
            try:
                r.delete(f"ratelimit:{self.name}:{key}")
            except Exception:
                pass


def rate_limit_dependency(max_requests: int, window_seconds: int = 60, name: str = "request"):
    limiter = RateLimiter(max_requests=max_requests, window_seconds=window_seconds, name=name)

    async def dependency(request: Request):
        limiter.check(request)

    dependency.limiter = limiter
    return dependency


def rate_limit(max_requests: int, window_seconds: int = 60, name: str = "request"):
    limiter = RateLimiter(max_requests=max_requests, window_seconds=window_seconds, name=name)

    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                request = kwargs.get("request")
                if not request:
                    for arg in args:
                        if isinstance(arg, Request):
                            request = arg
                            break
                if not request:
                    raise RuntimeError(f"Rate limited function {func.__name__} must accept request: Request")
                limiter.check(request)
                return await func(*args, **kwargs)
            async_wrapper.limiter = limiter
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                request = kwargs.get("request")
                if not request:
                    for arg in args:
                        if isinstance(arg, Request):
                            request = arg
                            break
                if not request:
                    raise RuntimeError(f"Rate limited function {func.__name__} must accept request: Request")
                limiter.check(request)
                return func(*args, **kwargs)
            sync_wrapper.limiter = limiter
            return sync_wrapper

    decorator.limiter = limiter
    return decorator


# Standard rate limiters
upload_rate_limiter = rate_limit_dependency(20, window_seconds=60, name="file upload")
pdf_rate_limiter = rate_limit_dependency(30, window_seconds=60, name="PDF generation")
bulk_import_rate_limiter = rate_limit_dependency(10, window_seconds=60, name="bulk import")

