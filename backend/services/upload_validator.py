"""Centralized Upload Validation & Storage Governance Service (P1-008, P1-018, P1-019).

Enforces:
1. Hardened MIME type verification using magic byte inspection (anti-MIME spoofing).
2. Canonical filename sanitization against path traversal, control chars, and null bytes.
3. Strict deployment profiles (dev, staging, production) with fail-closed storage rules.
4. Bounded file size caps.
"""

import os
import re
import io
import uuid
import logging
from typing import Optional, Set, Tuple, Literal
from fastapi import UploadFile, HTTPException

log = logging.getLogger("upload_validator")

# Supported deployment profiles
DeploymentProfile = Literal["dev", "staging", "production"]

DEFAULT_MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB
DEFAULT_IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_IMAGE_EXTENSIONS: Set[str] = {"jpg", "jpeg", "png", "webp"}
ALLOWED_DOCUMENT_EXTENSIONS: Set[str] = {"pdf", "csv", "xlsx", "xls"}

# Magic byte signatures
MAGIC_BYTES = {
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "webp": [b"RIFF"],  # followed by WEBP at offset 8
    "pdf": [b"%PDF"],
}


def get_deployment_profile() -> DeploymentProfile:
    """Return explicit deployment profile: 'production', 'staging', or 'dev'."""
    raw = (
        os.environ.get("DEPLOYMENT_PROFILE")
        or os.environ.get("ENVIRONMENT")
        or ("production" if os.environ.get("VERCEL") or os.environ.get("RENDER") else "dev")
    ).strip().lower()

    if raw in ("production", "prod"):
        return "production"
    if raw in ("staging", "stage"):
        return "staging"
    return "dev"


def sanitize_filename(filename: Optional[str], default_ext: str = "") -> str:
    """Sanitize filename to prevent directory traversal and filesystem attacks."""
    if not filename:
        return f"file_{uuid.uuid4().hex[:8]}.{default_ext}" if default_ext else f"file_{uuid.uuid4().hex[:8]}"

    # Strip path components and null bytes
    clean = os.path.basename(filename.replace("\\", "/"))
    clean = clean.replace("\x00", "").strip()

    # Reject directory traversal attempts
    if ".." in clean or clean.startswith("/") or clean.startswith("\\"):
        clean = re.sub(r"\.\.+", "", clean)

    # Allow only safe alphanumeric and standard filename characters
    clean = re.sub(r"[^a-zA-Z0-9_\-\. ]", "_", clean)
    clean = clean.strip(". ")

    if not clean:
        clean = f"upload_{uuid.uuid4().hex[:8]}"
        if default_ext:
            clean = f"{clean}.{default_ext}"

    # Cap length to 120 chars
    if len(clean) > 120:
        parts = clean.rsplit(".", 1)
        if len(parts) == 2:
            clean = parts[0][:100] + "." + parts[1]
        else:
            clean = clean[:120]

    return clean


sanitize_upload_filename = sanitize_filename


def verify_magic_bytes(header: bytes, ext: str) -> bool:
    """Verify file magic bytes match declared extension."""
    ext = ext.lower().lstrip(".")
    if ext in ("jpg", "jpeg"):
        return any(header.startswith(sig) for sig in MAGIC_BYTES["jpeg"])
    if ext == "png":
        return any(header.startswith(sig) for sig in MAGIC_BYTES["png"])
    if ext == "webp":
        return header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP"
    if ext == "pdf":
        return any(header.startswith(sig) for sig in MAGIC_BYTES["pdf"])
    if ext in ("csv", "txt"):
        # Text heuristic: ensure no binary null bytes in first 512 bytes
        return b"\x00" not in header[:512]
    if ext in ("xlsx", "xls"):
        # Excel zip header (PK\x03\x04) or legacy OLE CF header
        return header.startswith(b"PK\x03\x04") or header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    return True


async def validate_uploaded_file(
    file: UploadFile,
    allowed_extensions: Set[str],
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
    category_label: str = "file",
) -> Tuple[bytes, str]:
    """Validate uploaded file for extension, MIME magic bytes, size cap, and path safety.

    Returns (content_bytes, sanitized_filename).
    Raises HTTPException(400, 413) on validation violation.
    """
    if not file or not file.filename:
        raise HTTPException(400, f"No {category_label} uploaded.")

    # 1. Sanitize filename
    safe_filename = sanitize_filename(file.filename)
    ext = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""

    if not ext or ext not in allowed_extensions:
        allowed_str = ", ".join(sorted(allowed_extensions))
        raise HTTPException(
            400,
            f"Invalid {category_label} extension '{ext}'. Allowed extensions: {allowed_str}."
        )

    # 2. Bounded read
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            413,
            f"Image too large. File size exceeds maximum allowed limit of {max_mb} MB."
        )

    if len(content) == 0:
        raise HTTPException(400, f"Uploaded {category_label} is empty (0 bytes).")

    # 3. Magic bytes / Anti-MIME spoofing check
    header = content[:32]
    if not verify_magic_bytes(header, ext):
        raise HTTPException(
            400,
            f"File signature mismatch: file content does not match the '{ext}' extension. "
            "Anti-spoofing verification failed."
        )

    return content, safe_filename


def enforce_durable_storage_policy(storage_backend: Optional[str] = None):
    """Enforce that production deployments never fall back to local disk storage."""
    profile = get_deployment_profile()
    if profile in ("production", "staging"):
        if not storage_backend or storage_backend.lower() in ("local", "disk", "none"):
            raise HTTPException(
                503,
                f"Cloud object storage (ImageKit/S3) is required in {profile} environment. "
                "Local disk fallback is disabled to prevent data loss."
            )
