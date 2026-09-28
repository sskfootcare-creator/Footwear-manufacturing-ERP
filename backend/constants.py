"""Centralized Application Constants & Configuration Parameters.

Eliminates magic numbers across the SSK ERP application by providing
named, environment-configurable constants with sensible production defaults.
"""

import os

# ── File Upload & Image Security Limits (CODE-004, SEC-005, SEC-014) ──────────
# Default: 8 Megabytes maximum image file upload
MAX_IMAGE_UPLOAD_BYTES: int = int(os.environ.get("MAX_IMAGE_UPLOAD_BYTES", 8 * 1024 * 1024))

# Default: 10 Megapixels maximum pixel dimension (decompression bomb protection)
MAX_IMAGE_PIXELS: int = int(os.environ.get("MAX_IMAGE_PIXELS", 10_000_000))

# Allowed MIME types for image uploads
ALLOWED_IMAGE_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/jpg",
})

# Allowed file extensions for image uploads
ALLOWED_IMAGE_EXTENSIONS = frozenset({
    "jpg",
    "jpeg",
    "png",
    "webp",
    "gif",
})

# ── Dashboard & Reporting Cache Parameters (CODE-004, PERF-002, DB-005) ───────
# Default: 300 seconds (5 minutes) cache TTL for computed dashboard statistics
DASHBOARD_STATS_CACHE_TTL: int = int(os.environ.get("DASHBOARD_STATS_CACHE_TTL", 300))

# Default batch size when streaming large collections to prevent memory spikes
DASHBOARD_QUERY_BATCH_SIZE: int = int(os.environ.get("DASHBOARD_QUERY_BATCH_SIZE", 500))

# Upper safety bound on documents scanned for real-time dashboard calculations
DASHBOARD_MAX_DOCS_LIMIT: int = int(os.environ.get("DASHBOARD_MAX_DOCS_LIMIT", 10_000))

# Default pagination page size for list endpoints
DEFAULT_PAGE_SIZE: int = int(os.environ.get("DEFAULT_PAGE_SIZE", 50))
MAX_PAGE_SIZE: int = int(os.environ.get("MAX_PAGE_SIZE", 250))

# ── Authentication & Rate Limiting Constants ─────────────────────────────────
DEFAULT_RATE_LIMIT_LOGIN_MAX: int = int(os.environ.get("LOGIN_MAX_ATTEMPTS", 5))
DEFAULT_RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = int(os.environ.get("LOGIN_WINDOW_SECONDS", 900))  # 15 minutes
PASSWORD_RESET_TOKEN_TTL_HOURS: int = int(os.environ.get("PASSWORD_RESET_TTL_HOURS", 2))
REFRESH_TOKEN_TTL_DAYS: int = int(os.environ.get("REFRESH_TOKEN_DAYS", 7))
ACCESS_TOKEN_TTL_HOURS: int = int(os.environ.get("ACCESS_TOKEN_HOURS", 12))
