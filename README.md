# SSK Footcare - Footwear Manufacturing and ERP Backend

## Environment Configuration

The backend logic uses the `ENVIRONMENT` environment variable to control application startup behaviors, security settings, and admin account seeding.

### Environment Modes (`ENVIRONMENT`)

- **`development`** (default):
  - Seeds primary admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (defaults to `admin@example.com` / `admin123` if unset).
  - Seeds test admin (`admin@sskfootcare.com` / `Admin@123`) for local testing.
  - Seeds fallback example admin (`admin@example.com` / `admin123`).

- **`test`**:
  - Seeds primary admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
  - Seeds test admin (`admin@sskfootcare.com` / `Admin@123`) required for automated integration tests.
  - Skips example admin seeding (`admin@example.com`).

- **`production`**:
  - **`ADMIN_PASSWORD` is REQUIRED.** If `ADMIN_PASSWORD` is missing or empty, startup will immediately raise `RuntimeError` and fail to boot.
  - Seeds ONLY the env-configured primary admin (`ADMIN_EMAIL` / `ADMIN_PASSWORD`).
  - Skips hardcoded test and fallback admin accounts (`admin@sskfootcare.com` and `admin@example.com`) to eliminate production credential risks.

### Environment Variables (.env)

```env
ENVIRONMENT=production
MONGO_URL=mongodb://localhost:27017
DB_NAME=ssk_footwear_erp
JWT_SECRET=your_secure_jwt_secret_here
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=your_secure_admin_password
COOKIE_SECURE=true
```
