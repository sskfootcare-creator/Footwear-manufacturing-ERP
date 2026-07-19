"""Reusable Rate Limiting Dependencies and Decorators for FastAPI."""

from collections import defaultdict
from datetime import datetime, timezone
from functools import wraps
import inspect
import logging
from fastapi import HTTPException, Request

log = logging.getLogger("ssk.rate_limiter")


class RateLimiter:
    """In-memory sliding-window rate limiter per user/IP."""

    def __init__(self, max_requests: int, window_seconds: int = 60, name: str = "request"):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name
        self._history: dict = defaultdict(list)

    def get_client_key(self, request: Request) -> str:
        # Header override for test isolation
        test_ip = request.headers.get("x-test-rate-limit-client-ip")
        if test_ip:
            log.warning(f"Rate Limiter key test_ip={test_ip}")
            return f"test:{test_ip}"
        
        # User state (set by auth middleware or get_current_user if available)
        user = getattr(request.state, "user", None)
        if user and isinstance(user, dict) and "email" in user:
            log.warning(f"Rate Limiter key user_email={user['email']}")
            return f"user:{user['email']}"

        # Try to extract and decode JWT token to identify the user
        try:
            from auth import get_jwt_secret, JWT_ALGORITHM
            import jwt
            token = request.cookies.get("access_token")
            if not token:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
            if token:
                payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
                email = payload.get("email")
                if email:
                    log.warning(f"Rate Limiter key jwt_email={email}")
                    return f"user:{email}"
        except Exception as e:
            log.warning(f"Rate Limiter jwt decode failed: {e}")

        # Client IP fallback
        client_ip = request.client.host if request.client else "unknown"
        log.warning(f"Rate Limiter key ip={client_ip}")
        return f"ip:{client_ip}"

    def check(self, request: Request):
        key = self.get_client_key(request)
        now_ts = datetime.now(timezone.utc).timestamp()
        
        window = self.window_seconds
        test_window = request.headers.get("x-test-rate-limit-window")
        if test_window:
            try:
                window = int(test_window)
            except ValueError:
                pass

        window_start = now_ts - window

        # Prune expired timestamps
        self._history[key] = [t for t in self._history[key] if t > window_start]
        log.warning(f"Rate Limiter check: key={key}, history={self._history[key]}, max={self.max_requests}, window={window}")

        if len(self._history[key]) >= self.max_requests:
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

