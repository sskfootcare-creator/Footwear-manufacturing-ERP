# Enterprise Secret Management & Validation Architecture (DEPLOY-004)

## Overview
SSK ERP requires secure, auditable, and automated handling of sensitive credentials across all deployment environments (development, staging, production).

To prevent secret leakage, weak keys, or accidental exposure, the system introduces a dedicated Secrets Management module (`backend/secrets_manager.py`).

## Secret Hierarchy & Requirements
| Secret Key | Permitted Environments | Validation Rules & Constraints |
| :--- | :--- | :--- |
| `JWT_SECRET` | All | Minimum 32 characters, high entropy, not matching any known insecure default (`supersecretjwtkey12345!`, `secret`, `changeme`). Enforced at startup. |
| `MONGO_URL` | All | Valid MongoDB connection URI. In production, cannot point to `localhost` or unauthenticated endpoints. |
| `S3_BUCKET` | Production | Strict requirement in production (SEC-014). Prevents silent fallback to ephemeral container disk. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Production | Mandatory when S3_BUCKET is configured. |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | Optional / Prod | Required for Supabase ledger synchronization and double-entry bookkeeping. |

## Pluggable Secrets Providers
SSK ERP supports multiple secret storage backends via the `SecretProvider` interface:
1. **`EnvSecretProvider` (Default)**: Reads securely from environment variables provided by container runtimes or hosting platforms (Render, Vercel, ECS, Kubernetes Secrets).
2. **`VaultSecretProvider`**: Directly interfaces with HashiCorp Vault key-value engine with automatic token renewal.
3. **AWS Secrets Manager / GCP Secret Manager**: Extensible adapter for native cloud credential stores.

## Startup Validation & Failsafe Guarantees
During server initialization:
1. `validate_all_secrets(environment)` is invoked.
2. In **production** (`ENVIRONMENT=production`):
   - Missing or weak secrets immediately raise `RuntimeError` and abort container startup before opening listening ports.
   - Prevents booting into an insecure state.
3. In **development/test**:
   - Security warnings are logged without breaking local developer workflows.
4. All logs automatically mask sensitive tokens (`mask_secret()`) to prevent credential leakage in log aggregators (Datadog, CloudWatch, Papertrail).
