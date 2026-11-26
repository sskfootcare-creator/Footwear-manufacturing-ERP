"""A4 Scanned Pattern Digitization & Calibration Service.

Extracts true physical scale (1:1 mm), perimeter, net surface area (cm2),
and simplified vector geometry from A4 scanner beds (210mm x 297mm).
Supports automatic contrast thresholding (light or dark scanner lids),
noise filtering, and multiple pattern piece detection on a single page.
"""

import io
import math
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:
    cv2 = None

logger = logging.getLogger("pattern_scanner")

# Standard ISO 216 A4 Dimensions in Millimeters
A4_WIDTH_MM = 210.0
A4_HEIGHT_MM = 297.0
A4_ASPECT_RATIO = A4_HEIGHT_MM / A4_WIDTH_MM  # 1.4142857


def is_opencv_available() -> bool:
    return cv2 is not None


def extract_patterns_from_image_bytes(
    image_bytes: bytes,
    min_area_sqcm: float = 2.0,
    threshold_override: Optional[int] = None,
    invert_override: Optional[bool] = None,
    background_mode: str = "dark",
) -> Dict[str, Any]:
    """Process an A4 scanner image and extract calibrated pattern pieces.
    
    Args:
        image_bytes: Raw bytes of the uploaded scan (PNG, JPG, WebP, TIFF).
        min_area_sqcm: Minimum surface area in cm² to qualify as a valid pattern piece.
        threshold_override: Optional manual threshold (0-255). If None, uses Otsu.
        invert_override: Optional manual inversion flag.
        background_mode: 'dark' (default: dark scanner bed with contrast light pattern),
                         'light' (white scanner bed with dark pattern), or 'auto'.

    Returns:
        Dict containing calibration metadata, detected pattern pieces, and summary.
    """
    if not cv2:
        raise RuntimeError("OpenCV (cv2) is not available on this server environment")

    # 1. Load image via PIL to safely handle all image variants (including RGBA/CMYK)
    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        pil_img = pil_img.convert("RGB")
        img_np = np.array(pil_img)
        # Convert RGB to BGR for OpenCV
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    except Exception as e:
        raise ValueError(f"Failed to decode image data: {str(e)}")

    h_px, w_px = img_bgr.shape[:2]
    if h_px < 100 or w_px < 100:
        raise ValueError("Image resolution is too low for pattern measurement")

    # 2. Determine Page Orientation and Calibration Scale
    # An A4 flatbed scanner generates a full-page scan matching 210mm x 297mm
    is_portrait = h_px >= w_px
    page_w_mm = A4_WIDTH_MM if is_portrait else A4_HEIGHT_MM
    page_h_mm = A4_HEIGHT_MM if is_portrait else A4_WIDTH_MM

    # Compute scale factors
    scale_x = w_px / page_w_mm
    scale_y = h_px / page_h_mm
    scale_px_per_mm = (scale_x + scale_y) / 2.0
    dpi = round(scale_px_per_mm * 25.4, 1)

    # 3. Preprocessing: Grayscale & Background Contrast Detection
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Inspect background brightness from corner patches
    corners = [
        blurred[0:15, 0:15],
        blurred[0:15, -15:],
        blurred[-15:, 0:15],
        blurred[-15:, -15:],
    ]
    corner_mean = float(np.mean([np.mean(c) for c in corners]))
    auto_is_dark = corner_mean < 128.0

    # Determine threshold inversion based on background mode:
    # On dark background (light pattern): THRESH_BINARY selects bright pattern as foreground (255)
    # On light background (dark pattern): THRESH_BINARY_INV selects dark pattern as foreground (255)
    if invert_override is not None:
        use_inv = invert_override
    elif background_mode == "dark":
        use_inv = False
    elif background_mode == "light":
        use_inv = True
    else:  # auto
        use_inv = not auto_is_dark

    thresh_flag = cv2.THRESH_BINARY_INV if use_inv else cv2.THRESH_BINARY

    # 4. Thresholding
    if threshold_override is not None:
        _, thresh = cv2.threshold(blurred, int(threshold_override), 255, thresh_flag)
    else:
        # Otsu thresholding
        _, thresh = cv2.threshold(blurred, 0, 255, thresh_flag + cv2.THRESH_OTSU)

    # Morphological closing to seal pen marks, small staple holes, or surface grain
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    # Remove small specks
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel, iterations=1)

    # 5. Find Contours
    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    total_page_area_px = float(w_px * h_px)
    min_area_px = min_area_sqcm * 100.0 * (scale_px_per_mm ** 2)
    max_area_px = total_page_area_px * 0.94  # Filter out full scanner page contour

    detected_pieces: List[Dict[str, Any]] = []
    piece_idx = 1

    for c in contours:
        area_px = float(cv2.contourArea(c))
        if area_px < min_area_px or area_px > max_area_px:
            continue

        # Physical measurements
        area_mm2 = area_px / (scale_px_per_mm ** 2)
        area_sqcm = round(area_mm2 / 100.0, 2)
        area_sqdm = round(area_sqcm / 100.0, 4)

        # Axis-aligned bounding box
        bx, by, bw, bh = cv2.boundingRect(c)
        bbox_w_mm = round(bw / scale_px_per_mm, 1)
        bbox_h_mm = round(bh / scale_px_per_mm, 1)

        # Oriented bounding box (handles patterns placed at any diagonal angle)
        min_rect = cv2.minAreaRect(c)
        (mcx, mcy), (mw, mh), rot_angle = min_rect
        oriented_len_mm = round(max(mw, mh) / scale_px_per_mm, 1)
        oriented_wid_mm = round(min(mw, mh) / scale_px_per_mm, 1)

        # Perimeter
        perimeter_px = float(cv2.arcLength(c, True))
        perimeter_mm = round(perimeter_px / scale_px_per_mm, 1)

        # Polygon simplification for web rendering & nesting
        epsilon = 0.0025 * perimeter_px
        approx = cv2.approxPolyDP(c, epsilon, True)
        raw_pts = approx.reshape(-1, 2)

        # Convert to mm coordinates relative to page origin
        points_mm = [[round(pt[0] / scale_px_per_mm, 2), round(pt[1] / scale_px_per_mm, 2)] for pt in raw_pts]

        # Centered local coordinates (origin at top-left of piece bounding box)
        local_points_mm = [
            [round((pt[0] - bx) / scale_px_per_mm, 2), round((pt[1] - by) / scale_px_per_mm, 2)]
            for pt in raw_pts
        ]

        # Scaled SVG Path string in mm
        svg_path = ""
        if len(points_mm) > 2:
            path_parts = [f"M {points_mm[0][0]} {points_mm[0][1]}"]
            for pt in points_mm[1:]:
                path_parts.append(f"L {pt[0]} {pt[1]}")
            path_parts.append("Z")
            svg_path = " ".join(path_parts)

        # Local SVG Path string (for rendering single piece inside a box)
        local_svg_path = ""
        if len(local_points_mm) > 2:
            local_parts = [f"M {local_points_mm[0][0]} {local_points_mm[0][1]}"]
            for pt in local_points_mm[1:]:
                local_parts.append(f"L {pt[0]} {pt[1]}")
            local_parts.append("Z")
            local_svg_path = " ".join(local_parts)

        # Suggest component type based on aspect ratio and size
        suggested_name = _classify_piece_name(oriented_len_mm, oriented_wid_mm, area_sqcm, piece_idx)

        detected_pieces.append({
            "piece_id": f"p_{piece_idx}",
            "piece_name": suggested_name,
            "component": "upper",  # upper, lining, trim, counter, insole_covering
            "material_id": None,
            "material_name": None,
            "area_sqcm": area_sqcm,
            "area_sqdm": area_sqdm,
            "length_mm": oriented_len_mm,
            "width_mm": oriented_wid_mm,
            "raw_bbox_w_mm": bbox_w_mm,
            "raw_bbox_h_mm": bbox_h_mm,
            "perimeter_mm": perimeter_mm,
            "aspect_ratio": round(oriented_len_mm / max(oriented_wid_mm, 0.1), 2),
            "pieces_per_pair": 2,  # Standard: Left + Right
            "svg_polygon": svg_path,
            "local_svg_polygon": local_svg_path,
            "points_mm": points_mm,
            "local_points_mm": local_points_mm,
            "bbox_page": {
                "x_mm": round(bx / scale_px_per_mm, 1),
                "y_mm": round(by / scale_px_per_mm, 1),
                "w_mm": bbox_w_mm,
                "h_mm": bbox_h_mm,
            },
        })
        piece_idx += 1

    # Sort pieces from largest area to smallest
    detected_pieces.sort(key=lambda p: p["area_sqcm"], reverse=True)

    total_net_area_sqcm = round(sum(p["area_sqcm"] for p in detected_pieces), 2)
    total_net_pair_area_sqcm = round(sum(p["area_sqcm"] * p["pieces_per_pair"] for p in detected_pieces), 2)

    return {
        "ok": True,
        "calibration": {
            "page_width_mm": page_w_mm,
            "page_height_mm": page_h_mm,
            "image_width_px": w_px,
            "image_height_px": h_px,
            "orientation": "portrait" if is_portrait else "landscape",
            "scale_px_per_mm": round(scale_px_per_mm, 3),
            "dpi": dpi,
            "background_mode": background_mode,
            "background_detected": "dark" if auto_is_dark else "light",
        },
        "pieces_count": len(detected_pieces),
        "pattern_pieces": detected_pieces,
        "total_net_area_sqcm": total_net_area_sqcm,
        "total_net_pair_area_sqcm": total_net_pair_area_sqcm,
    }


def _classify_piece_name(len_mm: float, wid_mm: float, area_sqcm: float, idx: int) -> str:
    """Heuristic naming based on standard footwear pattern dimensions."""
    aspect = len_mm / max(wid_mm, 1.0)
    if aspect > 4.0:
        return f"Strap / Collar Band {idx}"
    if area_sqcm > 150.0:
        return f"Main Vamp {idx}"
    if area_sqcm > 75.0:
        return f"Side Quarter / Vamp {idx}"
    if area_sqcm > 30.0:
        return f"Counter / Overlay {idx}"
    return f"Pattern Piece {idx}"


def extract_piece_images_from_bytes(
    image_bytes: bytes,
    pieces: List[Dict[str, Any]],
    padding_mm: float = 5.0,
) -> Dict[str, bytes]:
    """Crop individual pattern piece images from the full A4 scan image.

    Returns a dictionary mapping piece_id -> JPEG image bytes.
    """
    if not pieces:
        return {}

    try:
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        logger.warning(f"Failed to open scan image for piece cropping: {e}")
        return {}

    w_px, h_px = pil_img.size
    is_portrait = h_px >= w_px
    page_w_mm = A4_WIDTH_MM if is_portrait else A4_HEIGHT_MM
    page_h_mm = A4_HEIGHT_MM if is_portrait else A4_WIDTH_MM
    scale_x = w_px / page_w_mm
    scale_y = h_px / page_h_mm
    scale_px_per_mm = (scale_x + scale_y) / 2.0

    cropped_map: Dict[str, bytes] = {}
    for p in pieces:
        pid = p.get("piece_id")
        bbox = p.get("bbox_page")
        if not pid or not bbox:
            continue
        x_mm = float(bbox.get("x_mm", 0))
        y_mm = float(bbox.get("y_mm", 0))
        w_mm = float(bbox.get("w_mm", 0))
        h_mm = float(bbox.get("h_mm", 0))
        if w_mm <= 0 or h_mm <= 0:
            continue

        x1 = max(0, int((x_mm - padding_mm) * scale_px_per_mm))
        y1 = max(0, int((y_mm - padding_mm) * scale_px_per_mm))
        x2 = min(w_px, int((x_mm + w_mm + padding_mm) * scale_px_per_mm))
        y2 = min(h_px, int((y_mm + h_mm + padding_mm) * scale_px_per_mm))

        if x2 <= x1 or y2 <= y1:
            continue

        try:
            crop = pil_img.crop((x1, y1, x2, y2))
            buf = io.BytesIO()
            crop.save(buf, format="JPEG", quality=88)
            cropped_map[pid] = buf.getvalue()
        except Exception as crop_err:
            logger.warning(f"Failed to crop piece {pid}: {crop_err}")

    return cropped_map
