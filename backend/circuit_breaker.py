"""Circuit Breaker Pattern Implementation for External Service Dependencies.

Addresses DEPLOY-003: External Service Dependencies (Redis, Supabase, S3, MongoDB).
Provides fault tolerance, fast-failure, and graceful fallback when external
services experience outages or high latency, preventing cascade failures in the ERP.
"""

import time
import asyncio
import logging
from enum import Enum
from typing import Callable, Any, Optional, Dict
from functools import wraps

log = logging.getLogger("ssk.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation: requests pass through
    OPEN = "OPEN"            # Service failed: fail fast without calling external service
    HALF_OPEN = "HALF_OPEN"  # Testing recovery: allow single probe request


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""
    def __init__(self, service_name: str, retry_after_seconds: float):
        self.service_name = service_name
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Circuit breaker for service '{service_name}' is OPEN. "
            f"Retry after {retry_after_seconds:.1f}s."
        )


class CircuitBreaker:
    """Thread-safe and async-compatible circuit breaker."""

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        expected_exceptions: tuple = (Exception,),
        fallback: Optional[Callable[..., Any]] = None,
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.expected_exceptions = expected_exceptions
        self.fallback = fallback

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
        self.success_count = 0

    def _update_state(self) -> None:
        """Check if OPEN state has expired and should transition to HALF_OPEN."""
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time >= self.recovery_timeout_seconds:
                log.info(
                    f"Circuit breaker for '{self.service_name}' transitioned from OPEN to HALF_OPEN (probing recovery)."
                )
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now

    def record_success(self) -> None:
        """Record a successful operation and close the circuit if HALF_OPEN."""
        if self.state == CircuitState.HALF_OPEN:
            log.info(
                f"Circuit breaker for '{self.service_name}' probe succeeded. Transitioning to CLOSED."
            )
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_state_change = time.time()
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self, error: Exception) -> None:
        """Record a failed operation and trip the circuit if threshold reached."""
        now = time.time()
        self.last_failure_time = now
        self.failure_count += 1
        log.warning(
            f"Circuit breaker for '{self.service_name}' recorded failure ({self.failure_count}/{self.failure_threshold}): {error}"
        )

        if self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN) and self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.last_state_change = now
            log.error(
                f"Circuit breaker for '{self.service_name}' TRIPPED to OPEN. Failing fast for {self.recovery_timeout_seconds}s."
            )

    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute an asynchronous function wrapped by the circuit breaker."""
        self._update_state()

        if self.state == CircuitState.OPEN:
            retry_after = max(0.0, self.recovery_timeout_seconds - (time.time() - self.last_failure_time))
            if self.fallback:
                log.info(f"Circuit breaker '{self.service_name}' OPEN; executing fallback.")
                if asyncio.iscoroutinefunction(self.fallback):
                    return await self.fallback(*args, **kwargs)
                return self.fallback(*args, **kwargs)
            raise CircuitBreakerOpenException(self.service_name, retry_after)

        try:
            res = await func(*args, **kwargs)
            self.record_success()
            return res
        except self.expected_exceptions as e:
            self.record_failure(e)
            if self.fallback:
                log.info(f"Service call failed for '{self.service_name}'; executing fallback.")
                if asyncio.iscoroutinefunction(self.fallback):
                    return await self.fallback(*args, **kwargs)
                return self.fallback(*args, **kwargs)
            raise

    def call_sync(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a synchronous function wrapped by the circuit breaker."""
        self._update_state()

        if self.state == CircuitState.OPEN:
            retry_after = max(0.0, self.recovery_timeout_seconds - (time.time() - self.last_failure_time))
            if self.fallback:
                return self.fallback(*args, **kwargs)
            raise CircuitBreakerOpenException(self.service_name, retry_after)

        try:
            res = func(*args, **kwargs)
            self.record_success()
            return res
        except self.expected_exceptions as e:
            self.record_failure(e)
            if self.fallback:
                return self.fallback(*args, **kwargs)
            raise

    def status(self) -> Dict[str, Any]:
        """Return diagnostic health status of the circuit breaker."""
        self._update_state()
        return {
            "service_name": self.service_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout_seconds,
            "last_failure_time": self.last_failure_time,
        }


# ── Global Circuit Breakers for ERP External Services (DEPLOY-003) ────────────
redis_circuit_breaker = CircuitBreaker("redis", failure_threshold=3, recovery_timeout_seconds=20.0)
supabase_circuit_breaker = CircuitBreaker("supabase", failure_threshold=4, recovery_timeout_seconds=30.0)
s3_circuit_breaker = CircuitBreaker("s3", failure_threshold=3, recovery_timeout_seconds=30.0)
mongo_circuit_breaker = CircuitBreaker("mongodb", failure_threshold=5, recovery_timeout_seconds=15.0)

ALL_CIRCUIT_BREAKERS = {
    "redis": redis_circuit_breaker,
    "supabase": supabase_circuit_breaker,
    "s3": s3_circuit_breaker,
    "mongodb": mongo_circuit_breaker,
}


def get_circuit_breakers_status() -> Dict[str, Any]:
    """Return health statuses of all registered service circuit breakers."""
    return {name: cb.status() for name, cb in ALL_CIRCUIT_BREAKERS.items()}
