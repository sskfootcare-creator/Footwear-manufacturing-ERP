"""Shared PDF image loader.

Historically pdf_card._img_from_dataurl only accepted `data:image/...` URLs, so
every uploaded photo — which is stored as a plain https / local URL — rendered
as "No Image" in printed Production Cards.  This module is the single place
every PDF generator loads images through so that fix stays fixed.

Contract:
    load_image_for_pdf(image_or_style, max_h_mm, max_w_mm) -> reportlab Image | None

`image_or_style` may be:
  - a dict with any/all of {url, image_url, image_display_url, image_thumbnail_url,
    display_url, thumbnail_url} keys — the loader picks the smallest variant
    that fits the requested print size, since dragging a 1600×1600 file down
    to a 46 mm print box is pure waste.
  - a bare string URL (data-URL, local /uploads/ URL, S3, or any external http).
  - None / "" — returns None (caller draws the No-Image placeholder).

The loader never raises: any timeout / 404 / decode error returns None so PDF
generation isn't broken by one missing photo.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any, Optional, Union

import requests
from reportlab.lib.units import mm
from reportlab.platypus import Image

log = logging.getLogger("ssk.pdf_image")

# Per-process cache — keyed by URL, holds the raw bytes.  Cleared explicitly
# between batches via clear_cache() so a long-running server doesn't leak.
_BYTES_CACHE: dict[str, bytes] = {}
_CACHE_MAX_ENTRIES = 128


def clear_cache() -> None:
    """Wipe the in-process byte cache — call at the start of a bulk PDF batch
    if you want each batch to see fresh S3 URLs, or leave alone for max reuse."""
    _BYTES_CACHE.clear()


def _cache_put(url: str, data: bytes) -> None:
    if len(_BYTES_CACHE) >= _CACHE_MAX_ENTRIES:
        # Cheap FIFO eviction — pop the oldest key.  We don't need LRU precision
        # here, we just need to bound memory.
        try:
            _BYTES_CACHE.pop(next(iter(_BYTES_CACHE)))
        except StopIteration:
            pass
    _BYTES_CACHE[url] = data


def _pick_smallest_variant(image: dict, max_w_mm: float, max_h_mm: float) -> list[str]:
    """Return a preference-ordered list of URLs to try, smallest first when
    the box is smaller than the display variant's rough intended size."""
    display   = image.get("display_url") or image.get("image_display_url") or ""
    thumbnail = image.get("thumbnail_url") or image.get("image_thumbnail_url") or ""
    original  = image.get("url") or image.get("image_url") or ""

    # Rough heuristic: the display variant is capped at 600 px, the thumbnail
    # at 150 px, the original at 1600.  If the print box is postage-stamp
    # sized, thumbnail is enough and cheapest.
    largest_dim_mm = max(max_w_mm, max_h_mm)
    if largest_dim_mm <= 20 and thumbnail:
        chain = [thumbnail, display, original]
    else:
        chain = [display, thumbnail, original]

    # Also try deriving the display URL from a legacy .../original.jpg URL that
    # only exposes `url` — this handles rows created before Phase 1 stored the
    # three-variant response but that happen to sit on the new /uploads/images/
    # tree we generate.  Never risks a crash — just adds another candidate.
    if original.endswith("/original.jpg"):
        derived_display = original.rsplit("/", 1)[0] + "/display.jpg"
        derived_thumb   = original.rsplit("/", 1)[0] + "/thumb.jpg"
        chain = [derived_display, derived_thumb] + chain

    # Deduplicate while preserving order and stripping empty strings.
    seen: set[str] = set()
    out: list[str] = []
    for u in chain:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _fetch_bytes(url: str) -> Optional[bytes]:
    """Best-effort URL → bytes.  data-URL, local /uploads/, or external http.

    Returns None on any failure so the caller falls through to the next URL
    (or, ultimately, the No-Image placeholder)."""
    if not url:
        return None
    if url in _BYTES_CACHE:
        return _BYTES_CACHE[url]

    # data URL — no I/O
    if url.startswith("data:image"):
        try:
            _, b64 = url.split(",", 1)
            data = base64.b64decode(b64)
            _cache_put(url, data)
            return data
        except Exception as e:
            log.warning("data-URL decode failed: %s", e)
            return None

    # Local /uploads/ URL — read the file straight off disk.  This is the fast
    # path Phase 1 built resolve_local_upload_path() specifically to enable —
    # no self-HTTP round-trip that would deadlock a single-worker uvicorn.
    # Works for absolute AND relative shapes ("/api/uploads/..." or "http://…/api/uploads/...").
    try:
        # Late import to avoid a circular dep at module-load time.
        from server import resolve_local_upload_path
        local_path = resolve_local_upload_path(url)
        if local_path:
            with open(local_path, "rb") as f:
                data = f.read()
            _cache_put(url, data)
            return data
    except Exception as e:
        log.warning("Local upload read failed for %s: %s", url, e)

    # If we got here with a relative URL (no scheme), we can't fetch it via
    # requests.  Bail — the caller falls through to the next candidate.
    if not url.startswith(("http://", "https://")):
        log.warning("Relative image URL %s couldn't be resolved locally.", url)
        return None

    # External URL (S3, OneDrive, CDN, …).  Short timeout so one dead link
    # doesn't wedge PDF generation for an entire batch.
    try:
        r = requests.get(url, timeout=5, stream=False)
        if r.status_code == 200 and r.content:
            _cache_put(url, r.content)
            return r.content
        log.warning("Image fetch got HTTP %s for %s", r.status_code, url)
    except Exception as e:
        log.warning("Image fetch failed for %s: %s", url, e)
    return None


def _fit_image(bio: io.BytesIO, max_w_mm: float, max_h_mm: float) -> Optional[Image]:
    """Wrap bytes in a reportlab Image scaled into (max_w_mm × max_h_mm)."""
    try:
        img = Image(bio)
        ratio = img.imageWidth / img.imageHeight if img.imageHeight else 1
        target_w_pt = max_w_mm * mm
        target_h_pt = max_h_mm * mm
        if ratio > (target_w_pt / target_h_pt):
            img.drawWidth  = target_w_pt
            img.drawHeight = target_w_pt / ratio
        else:
            img.drawHeight = target_h_pt
            img.drawWidth  = target_h_pt * ratio
        return img
    except Exception as e:
        log.warning("reportlab Image decode failed: %s", e)
        return None


def load_image_for_pdf(
    image_or_style: Union[dict, str, None],
    max_h_mm: float = 50,
    max_w_mm: float = 50,
) -> Optional[Image]:
    """Return a sized reportlab Image ready for a Table cell, or None.

    Never raises — every failure path (bad URL, timeout, decode error, missing
    field) returns None so PDF generation continues with a No-Image placeholder.
    """
    if not image_or_style:
        return None

    # Accept either the full image dict, a style dict, or a plain URL string.
    if isinstance(image_or_style, dict):
        image_dict = image_or_style
    else:
        image_dict = {"url": str(image_or_style)}

    for candidate_url in _pick_smallest_variant(image_dict, max_w_mm, max_h_mm):
        data = _fetch_bytes(candidate_url)
        if not data:
            continue
        img = _fit_image(io.BytesIO(data), max_w_mm=max_w_mm, max_h_mm=max_h_mm)
        if img is not None:
            return img
    return None
