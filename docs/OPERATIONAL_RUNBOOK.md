# Enterprise Operational Runbook & Observability Guide (P1-020)

## 1. Overview & Architecture

This runbook provides on-call engineers, DevOps teams, and site reliability engineers with complete diagnostics, alert thresholds, and operational troubleshooting procedures for the SSK Footwear ERP system.

---

## 2. Health Check & Dependency Matrix

The application exposes two standardized health probes:
- `GET /healthz`: Fast liveness check (probes process availability and immediate event loop health).
- `GET /readyz`: Deep readiness check validating all downstream backing services.

### Dependency Health Matrix Response Format
A request to `GET /readyz` returns JSON with HTTP `200` (healthy) or HTTP `503` (degraded/unready):

```json
{
  "status": "ready",
  "deployment_profile": "production",
  "dependencies": {
    "mongodb": {
      "status": "connected",
      "latency_ms": 4.2
    },
    "jwt_auth": {
      "status": "healthy",
      "secret_configured": true
    },
    "object_storage": {
      "status": "configured",
      "driver": "imagekit",
      "durable": true
    },
    "supabase": {
      "status": "not_configured"
    },
    "circuit_breakers": {
      "status": "closed",
      "active_count": 0
    }
  },
  "timestamp": "2026-10-20T13:30:00Z"
}
```

### Dependency Evaluation Criteria
| Dependency | Healthy Condition | Warning / Degraded Trigger | Hard Failure (503) |
| :--- | :--- | :--- | :--- |
| **MongoDB** | Ping command responds < 50ms | Latency between 50ms and 200ms | Ping timeout or connection refused |
| **JWT Auth** | Secret verified & cryptographically strong | Using local auto-generated key in dev | Insecure default detected in production |
| **Object Storage** | S3 or ImageKit connected | Ephemeral storage in dev/test | Local fallback in production profile |
| **Circuit Breakers**| State `CLOSED` | State `HALF-OPEN` | State `OPEN` on critical database paths |

---

## 3. Alert Rules & Thresholds

| Alert Identifier | Metric / Trigger | Severity | Action Required |
| :--- | :--- | :--- | :--- |
| `ERR_MONGO_DOWN` | `readyz` returns `mongodb.status != "connected"` for 3 consecutive checks (30s) | P1 - Critical | Escalate to on-call DBA immediately; check cluster connectivity. |
| `ERR_MONGO_LATENCY` | MongoDB response time > 200ms for 5 minutes | P2 - High | Check active long-running queries in `db.currentOp()`, bounded collection limits. |
| `ERR_EPHEMERAL_PROD` | Production environment running without durable S3/ImageKit | P1 - Critical | Halts server boot. Supply `AWS_ACCESS_KEY_ID` or `IMAGEKIT_PRIVATE_KEY`. |
| `ERR_STOCK_INVARIANT` | Attempted stock deduction resulting in negative inventory | P2 - High | Review `audit_logs` for `action=override_stock_deduction`. |
| `ERR_IMPORT_DUPLICATE`| Spike in quarantined duplicates (`online_order_exceptions` > 100/hr) | P3 - Medium | Inspect marketplace batch files for duplicate order release IDs. |

---

## 4. Incident Response Runbooks

### Incident A: MongoDB Unreachable / Connection Dropped
1. **Symptoms:** `/readyz` returns HTTP 503; logs show `ServerSelectionTimeoutError` or `Connection refused`.
2. **Diagnostic Commands:**
   ```bash
   # Check pod / service status
   kubectl get pods -l app=mongodb
   # Test raw connectivity
   nc -zv $MONGO_HOST 27017
   ```
3. **Remediation:**
   - Verify network security groups or MongoDB Atlas IP allow-list.
   - If connection pool exhausted, inspect `maxPoolSize` in `server.py` and restart backend workers gracefully.

---

### Incident B: JWT Secret Invalidation / Auth Lockout
1. **Symptoms:** Server fails startup with `RuntimeError: SEC-001: Production deployment requires a secure, non-default JWT_SECRET`.
2. **Remediation:**
   - Ensure the secret management engine (e.g. Doppler, AWS Secrets Manager, Kubernetes Secret) injects a high-entropy string:
     ```bash
     openssl rand -hex 32
     ```
   - Update `JWT_SECRET` in environment variables and restart.

---

### Incident C: Storage Policy Violation in Production
1. **Symptoms:** `/upload/image` throws HTTP 500: `Durable object storage required in production profile`.
2. **Remediation:**
   - Check if ImageKit or S3 credentials expired or were revoked.
   - Set `IMAGEKIT_PUBLIC_KEY`, `IMAGEKIT_PRIVATE_KEY`, `IMAGEKIT_URL_ENDPOINT` or S3 credentials.

---

### Incident D: Distributed Migration Lock Contention
1. **Symptoms:** Backend deployment stuck on startup: `Could not acquire migration lock; another worker may be executing migrations`.
2. **Remediation:**
   - Check if a previous container crash left `locked: true`:
     ```bash
     python -c "import asyncio, server; asyncio.run(server.db.migration_locks.find_one({'_id': 'global_migration_lock'}))"
     ```
   - Release the stale lock:
     ```bash
     python backend/db/backup_restore.py --rollback-migration 000
     ```

---

### Incident E: SKU Mapping Review Queue Overflow
1. **Symptoms:** New marketplace orders fail style resolution and enter `sku_map_review_queue`.
2. **Remediation:**
   - Open ERP Admin Portal -> SKU Mapping -> Review Queue.
   - Review low confidence score items (`confidence_score < 0.85`).
   - Map unresolved external SKU to the canonical ERP style and color code.
