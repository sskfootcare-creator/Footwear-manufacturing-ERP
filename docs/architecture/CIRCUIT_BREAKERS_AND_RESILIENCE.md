# External Service Dependencies & Circuit Breaker Architecture (DEPLOY-003)

## Overview
SSK ERP integrates with four primary external dependencies:
1. **MongoDB**: Primary operational datastore (documents, transactions, audit logs).
2. **Supabase (PostgreSQL / Auth)**: Double-entry financial journal system of record and OAuth provider.
3. **Redis**: Cluster-wide sliding window rate limiting and distributed caching.
4. **AWS S3**: Durable binary asset storage for design sketches, carton labels, and invoices.

Prior to audit remediation, these external services represented potential cascading single points of failure without standardized circuit breakers or health tracking.

## Circuit Breaker Implementation (`backend/circuit_breaker.py`)
Each external service dependency is monitored by a stateful circuit breaker implementing the standard 3-state pattern:
- **CLOSED**: Normal operation. Outgoing requests are executed normally. Success resets failure counters.
- **OPEN**: Tripped state. If failures cross the threshold (default: 3-5 consecutive failures), the breaker trips to OPEN. All subsequent calls immediately fail fast or return safe fallback values without incurring connection timeouts or hammering degraded dependencies.
- **HALF_OPEN**: Recovery probe. After a configured recovery timeout (default: 15-30s), one probe request is permitted through. If successful, the circuit resets to CLOSED. If it fails, it returns to OPEN for another cooldown period.

## Failure Isolation & Fallback Policy
| Dependency | Primary Function | Circuit Breaker Policy | Graceful Degradation / Fallback |
| :--- | :--- | :--- | :--- |
| **Redis** | Rate limiting & cache | Fail threshold: 3, Timeout: 20s | Falls back immediately to bounded in-memory sliding-window limiter; zero user interruption. |
| **Supabase** | Financial ledger sync | Fail threshold: 4, Timeout: 30s | Sync events captured to `supabase_sync_failures` collection for automatic replay via `retry_failed_syncs`. |
| **Supabase Auth** | User authentication | Fail threshold: 3, Timeout: 30s | Falls back to internal bcrypt password validation for seeded/local administrative accounts. |
| **AWS S3** | Image/PDF storage | Fail threshold: 3, Timeout: 30s | In development/test, falls back to local uploads. In production, alerts operator with retry metadata. |
| **MongoDB** | Primary datastore | Fail threshold: 5, Timeout: 15s | Liveness `/healthz` stays up, `/readyz` fails fast with 503 so load balancers stop routing traffic. |

## Monitoring & Health Probes
The health status of all registered circuit breakers is exposed through the `/readyz` readiness probe:
```json
{
  "status": "ready",
  "circuit_breakers": {
    "redis": {"state": "CLOSED", "failure_count": 0},
    "supabase": {"state": "CLOSED", "failure_count": 0},
    "s3": {"state": "CLOSED", "failure_count": 0},
    "mongodb": {"state": "CLOSED", "failure_count": 0}
  }
}
```
