"""
Online Returns Engine: Myntra Return Analytics, Prescriptive Reduction Engine & Impact Verification.
"""
import io
import csv
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from collections import defaultdict
from fastapi import APIRouter, Request, UploadFile, File, Query, HTTPException, Depends
from pydantic import BaseModel
from bson import ObjectId

from auth import require_roles

def get_db():
    import server
    return server.db

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

online_returns_router = APIRouter(prefix="/api/online-returns", tags=["Online Returns Engine"])

# Business classification taxonomy for footwear returns
REASON_CATEGORIES = {
    "SIZING_FIT": [
        "size too small", "size too big", "size is different", 
        "size is too large", "i did not like the fit", "wrong size"
    ],
    "QUALITY_DEFECT": [
        "received a poor quality product", "product was defective", 
        "product was dirty and had stains", "product was damaged", 
        "product looked old", "defective product was delivered"
    ],
    "CATALOG_MISMATCH": [
        "product image was better than the actual product", 
        "color is different"
    ],
    "DISPATCH_ERROR": [
        "received a completely different product"
    ],
    "BUYER_REMORSE": [
        "i do not need it anymore", "found a better price on myntra", 
        "generic return reason"
    ],
    "COURIER_RTO": [
        "rto", "courier return", "undelivered"
    ]
}

def classify_return_reason(reason_str: str, status_str: str) -> str:
    r_lower = (reason_str or "").strip().lower()
    s_lower = (status_str or "").strip().lower()
    if s_lower == "rto" or "rto" in r_lower:
        return "COURIER_RTO"
    for category, keywords in REASON_CATEGORIES.items():
        for kw in keywords:
            if kw in r_lower:
                return category
    return "OTHER"

def parse_sku_details(seller_sku: str) -> Dict[str, str]:
    raw = (seller_sku or "").strip()
    if not raw:
        return {"style_code": "UNKNOWN", "color": "", "size": "", "sku": raw}
    
    # Matches patterns like FLL_AK_005_GO-7, CCE-051-TN-41, CC-058-BR-38
    m = re.match(r"^([A-Za-z0-9_\-]+)[-_]([0-9]+(?:\.[0-9]+)?)$", raw)
    if m:
        root_and_color = m.group(1)
        size = m.group(2)
        parts = re.split(r"[-_]", root_and_color)
        if len(parts) >= 2 and len(parts[-1]) <= 4 and parts[-1].isalpha():
            color = parts[-1]
            style_code = "_".join(parts[:-1])
        else:
            color = ""
            style_code = root_and_color
        return {"style_code": style_code, "color": color, "size": size, "sku": raw}
    
    return {"style_code": raw, "color": "", "size": "", "sku": raw}

class AppliedFixPayload(BaseModel):
    style_code: str
    action_type: str  # LAST_ADJUSTMENT | CATALOG_RESHOOT | QC_GATE | LISTING_ADVICE | DISPATCH_SCAN
    category: str     # SIZING_FIT | QUALITY_DEFECT | CATALOG_MISMATCH | DISPATCH_ERROR | COURIER_RTO
    title: str
    description: str
    target_month: Optional[str] = None
    applied_date: str
    target_reduction_pct: Optional[float] = 30.0

class StylePhotoPayload(BaseModel):
    style_code: str
    image_url: str

def get_footwear_placeholder_image(style_code: str) -> str:
    s_upper = (style_code or "").upper()
    if "SLIDE" in s_upper or "SL" in s_upper:
        return "/company/braided_slide.jpg"
    elif "FL" in s_upper or "FLAT" in s_upper or "SANDAL" in s_upper or "CC" in s_upper:
        return "/company/laser_cut_flat.jpg"
    elif "ETH" in s_upper or "JUTTI" in s_upper or "KOLHA" in s_upper:
        return "/company/ethnic_embroidered.jpg"
    elif "DERBY" in s_upper or "FORMAL" in s_upper:
        return "/company/black_derby.jpg"
    return "/company/classic_oxford.jpg"

@online_returns_router.post("/upload")
async def upload_myntra_returns(
    request: Request,
    file: UploadFile = File(...),
    month: str = Query(..., description="Reporting month YYYY-MM (e.g. 2026-08)"),
    platform: str = Query("myntra", description="Platform identifier"),
):
    db = get_db()
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("latin-1")
    
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="Empty or invalid CSV file")
    
    batch_id = str(ObjectId())
    batch_month = month.strip()
    records = []
    
    for r in rows:
        seller_sku = r.get("seller_sku_code") or r.get("seller_sku") or ""
        sku_info = parse_sku_details(seller_sku)
        status_val = (r.get("status") or "").strip()
        reason_val = (r.get("return_reason") or "").strip()
        category = classify_return_reason(reason_val, status_val)
        
        created_date = (r.get("return_created_date") or r.get("order_rto_date") or r.get("order_created_date") or "").strip()
        
        rec = {
            "batch_id": batch_id,
            "platform": platform.lower(),
            "month": batch_month,
            "seller_sku_code": seller_sku,
            "style_code": sku_info["style_code"],
            "color": sku_info["color"],
            "size": sku_info["size"],
            "brand": (r.get("brand") or "").strip(),
            "myntra_sku_code": (r.get("myntra_sku_code") or "").strip(),
            "status": status_val,
            "return_mode": (r.get("return_mode") or "").strip(),
            "return_reason": reason_val,
            "reason_category": category,
            "order_id": (r.get("order_id") or "").strip(),
            "seller_order_id": (r.get("seller_order_id") or "").strip(),
            "forward_tracking": (r.get("forward_tracking_number") or "").strip(),
            "return_tracking": (r.get("return_tracking_number") or "").strip(),
            "order_date": (r.get("order_created_date") or "").strip(),
            "return_date": created_date,
            "uploaded_at": now_iso(),
        }
        records.append(rec)
    
    if records:
        await db.online_returns_records.delete_many({"month": batch_month, "platform": platform.lower()})
        await db.online_returns_records.insert_many(records)
        
        await db.online_returns_batches.update_one(
            {"month": batch_month, "platform": platform.lower()},
            {"$set": {
                "batch_id": batch_id,
                "month": batch_month,
                "platform": platform.lower(),
                "filename": file.filename,
                "total_rows": len(records),
                "uploaded_at": now_iso(),
            }},
            upsert=True
        )
        
    return {
        "success": True,
        "batch_id": batch_id,
        "month": batch_month,
        "rows_processed": len(records),
        "message": f"Successfully ingested {len(records)} returns for {batch_month}"
    }

@online_returns_router.get("/analytics")
async def get_returns_analytics(
    request: Request,
    month: Optional[str] = Query(None, description="Month YYYY-MM"),
    platform: str = Query("myntra"),
    style_code: Optional[str] = Query(None),
):
    db = get_db()
    
    # Auto select latest month if not specified
    if not month:
        latest = await db.online_returns_batches.find_one({"platform": platform.lower()}, sort=[("month", -1)])
        month = latest.get("month", "2026-08") if latest else "2026-08"
        
    q: Dict[str, Any] = {"month": month, "platform": platform.lower()}
    if style_code and isinstance(style_code, str):
        q["style_code"] = style_code.strip()
        
    records = await db.online_returns_records.find(q).to_list(10000)
    
    total_returns = len(records)
    rto_count = sum(1 for r in records if r.get("status") == "RTO" or r.get("reason_category") == "COURIER_RTO")
    customer_return_count = total_returns - rto_count
    
    # Breakdown by Category
    category_counts = defaultdict(int)
    reason_counts = defaultdict(int)
    styles_map = defaultdict(lambda: {
        "style_code": "", "brand": "", "total": 0, "customer_returns": 0, "rto": 0,
        "reasons": defaultdict(int), "categories": defaultdict(int),
        "sizes": defaultdict(lambda: {"total": 0, "too_small": 0, "too_big": 0, "other": 0})
    })
    
    for r in records:
        cat = r.get("reason_category") or "OTHER"
        reason = r.get("return_reason") or "Not Specified"
        category_counts[cat] += 1
        reason_counts[reason] += 1
        
        st = r.get("style_code") or "UNKNOWN"
        entry = styles_map[st]
        entry["style_code"] = st
        entry["brand"] = r.get("brand") or entry["brand"] or "SSK"
        entry["total"] += 1
        if r.get("status") == "RTO":
            entry["rto"] += 1
        else:
            entry["customer_returns"] += 1
        entry["reasons"][reason] += 1
        entry["categories"][cat] += 1
        
        sz = r.get("size")
        if sz:
            s_data = entry["sizes"][sz]
            s_data["total"] += 1
            r_low = reason.lower()
            if "small" in r_low:
                s_data["too_small"] += 1
            elif "big" in r_low or "large" in r_low:
                s_data["too_big"] += 1
            else:
                s_data["other"] += 1
                
    # Lookup style images from db.online_style_photos, db.styles, and db.sku_map
    all_codes = list(styles_map.keys())
    custom_photos = {}
    async for d in db.online_style_photos.find({"style_code": {"$in": all_codes}}):
        if d.get("image_url"):
            custom_photos[d["style_code"]] = d["image_url"]
            
    style_alt_codes = [c.replace("_", "-") for c in all_codes] + [c.replace("-", "_") for c in all_codes]
    style_docs = await db.styles.find(
        {"code": {"$in": list(set(all_codes + style_alt_codes))}},
        {"code": 1, "image_url": 1, "image_thumbnail_url": 1, "image_display_url": 1}
    ).to_list(500)
    styles_img_map = {}
    for sd in style_docs:
        img = sd.get("image_thumbnail_url") or sd.get("image_url") or sd.get("image_display_url")
        if img:
            styles_img_map[sd["code"]] = img
            styles_img_map[sd["code"].replace("-", "_")] = img
            styles_img_map[sd["code"].replace("_", "-")] = img
            
    sku_docs = await db.sku_map.find(
        {"style_code": {"$in": list(set(all_codes + style_alt_codes))}},
        {"style_code": 1, "image_url": 1}
    ).to_list(500)
    for sk in sku_docs:
        img = sk.get("image_url")
        if img and sk.get("style_code"):
            st_c = sk["style_code"]
            if st_c not in styles_img_map:
                styles_img_map[st_c] = img
                styles_img_map[st_c.replace("-", "_")] = img

    # Format styles ranking list
    ranked_styles = []
    for st, d in styles_map.items():
        top_reason = max(d["reasons"].items(), key=lambda kv: kv[1])[0] if d["reasons"] else "None"
        top_category = max(d["categories"].items(), key=lambda kv: kv[1])[0] if d["categories"] else "OTHER"
        img_url = (
            custom_photos.get(st)
            or styles_img_map.get(st)
            or styles_img_map.get(st.replace("_", "-"))
            or get_footwear_placeholder_image(st)
        )
        ranked_styles.append({
            "style_code": st,
            "brand": d["brand"],
            "image_url": img_url,
            "total_returns": d["total"],
            "customer_returns": d["customer_returns"],
            "rto_returns": d["rto"],
            "top_reason": top_reason,
            "top_category": top_category,
            "categories": dict(d["categories"]),
            "reasons": dict(d["reasons"]),
            "sizes": dict(d["sizes"]),
            "estimated_reverse_freight": d["total"] * 85.0, # Average ₹85 reverse freight per return
        })
    ranked_styles.sort(key=lambda s: s["total_returns"], reverse=True)
    
    # Available months in DB
    distinct_months = await db.online_returns_batches.distinct("month", {"platform": platform.lower()})
    
    return {
        "month": month,
        "available_months": sorted(distinct_months, reverse=True) if distinct_months else [month],
        "total_returns": total_returns,
        "customer_returns": customer_return_count,
        "rto_returns": rto_count,
        "category_breakdown": dict(category_counts),
        "top_reasons": sorted([{"reason": k, "count": v} for k, v in reason_counts.items()], key=lambda x: x["count"], reverse=True)[:10],
        "styles": ranked_styles,
        "total_reverse_freight_damage": round(total_returns * 85.0, 2),
    }

@online_returns_router.get("/prescriptions")
async def get_return_prescriptions(
    request: Request,
    month: Optional[str] = Query(None),
    platform: str = Query("myntra"),
):
    analytics = await get_returns_analytics(request, month=month, platform=platform, style_code=None)
    styles = analytics.get("styles", [])
    
    prescriptions = []
    for s in styles:
        if s["total_returns"] < 2:
            continue
            
        cats = s.get("categories", {})
        reasons = s.get("reasons", {})
        sizes = s.get("sizes", {})
        total = s["total_returns"]
        
        # Analyze sizing skew
        sizing_count = cats.get("SIZING_FIT", 0)
        too_small_total = sum(v.get("too_small", 0) for v in sizes.values())
        too_big_total = sum(v.get("too_big", 0) for v in sizes.values())
        
        rec_list = []
        priority = "MEDIUM"
        
        if sizing_count > 0 and (sizing_count / total) >= 0.35:
            if too_big_total > too_small_total:
                priority = "HIGH"
                rec_list.append({
                    "action_type": "LAST_ADJUSTMENT",
                    "category": "SIZING_FIT",
                    "title": f"Pattern Reduction: Style runs large ({too_big_total} returns)",
                    "recommendation": "Shave 2.5mm from instep and ball girth on lasting mold. Add marketplace bullet: 'Runs slightly large, order 1 size down if between sizes'.",
                    "expected_impact": "Reduces sizing returns by 40-50%"
                })
            else:
                priority = "HIGH"
                rec_list.append({
                    "action_type": "LAST_ADJUSTMENT",
                    "category": "SIZING_FIT",
                    "title": f"Pattern Widening: Style runs small ({too_small_total} returns)",
                    "recommendation": "Expand toe-box width by 3.5mm and relax vamp throat. Add marketplace bullet: 'Comfort slim-fit, recommend choosing 1 size up'.",
                    "expected_impact": "Reduces tight-fit complaints by 35-45%"
                })
                
        if cats.get("CATALOG_MISMATCH", 0) > 0 and (cats.get("CATALOG_MISMATCH", 0) / total) >= 0.20:
            rec_list.append({
                "action_type": "CATALOG_RESHOOT",
                "category": "CATALOG_MISMATCH",
                "title": "Color & Image Recalibration",
                "recommendation": "Re-photograph under 5500K CRI>95 neutral studio daylight. Reduce saturation boost in post-processing to avoid customer expectation mismatch.",
                "expected_impact": "Reduces 'image better than actual' by 60%"
            })
            
        if cats.get("QUALITY_DEFECT", 0) > 0 and (cats.get("QUALITY_DEFECT", 0) / total) >= 0.18:
            priority = "CRITICAL"
            rec_list.append({
                "action_type": "QC_GATE",
                "category": "QUALITY_DEFECT",
                "title": "Factory QC Gate & Protection Wrapping",
                "recommendation": "Enforce 100% sole-adhesion bonding pull-test and introduce moisture barrier tissue wrapping to prevent upper scuffing/stains during transit.",
                "expected_impact": "Eliminates defect and stain return claims"
            })
            
        if cats.get("DISPATCH_ERROR", 0) > 0:
            rec_list.append({
                "action_type": "DISPATCH_SCAN",
                "category": "DISPATCH_ERROR",
                "title": "Double Barcode Verification",
                "recommendation": "Implement 2-scan barcode validation at packing station to prevent box/label cross-mismatch before shipment sealing.",
                "expected_impact": "Eliminates wrong SKU dispatches"
            })
            
        if s.get("rto_returns", 0) > 0 and (s.get("rto_returns", 0) / total) >= 0.30:
            rec_list.append({
                "action_type": "LISTING_ADVICE",
                "category": "COURIER_RTO",
                "title": "High Courier Non-Delivery / RTO Rate",
                "recommendation": "Monitor high COD failure pincodes and prioritize platform logistics partners with automated SMS pre-delivery confirmation.",
                "expected_impact": "Decreases courier RTO rate by 20%"
            })
            
        if rec_list:
            prescriptions.append({
                "style_code": s["style_code"],
                "brand": s["brand"],
                "image_url": s.get("image_url") or get_footwear_placeholder_image(s["style_code"]),
                "priority": priority,
                "total_returns": s["total_returns"],
                "actions": rec_list,
            })
            
    return {"month": analytics.get("month"), "prescriptions": prescriptions}

@online_returns_router.post("/style-photo")
async def update_style_photo(payload: StylePhotoPayload, request: Request):
    db = get_db()
    st = payload.style_code.strip()
    img = payload.image_url.strip()
    if not st or not img:
        raise HTTPException(status_code=400, detail="style_code and image_url are required")
    await db.online_style_photos.update_one(
        {"style_code": st},
        {"$set": {"style_code": st, "image_url": img, "updated_at": now_iso()}},
        upsert=True
    )
    await db.styles.update_one(
        {"$or": [{"code": st}, {"code": st.replace("_", "-")}]},
        {"$set": {"image_url": img, "image_thumbnail_url": img, "image_display_url": img}}
    )
    return {"success": True, "style_code": st, "image_url": img}

@online_returns_router.post("/actions")
async def record_applied_fix(payload: AppliedFixPayload, request: Request):
    db = get_db()
    u = getattr(request.state, "user", None)
    doc = {
        "style_code": payload.style_code.strip(),
        "action_type": payload.action_type,
        "category": payload.category,
        "title": payload.title,
        "description": payload.description,
        "target_month": payload.target_month,
        "applied_date": payload.applied_date,
        "target_reduction_pct": payload.target_reduction_pct or 30.0,
        "status": "APPLIED",
        "created_at": now_iso(),
        "user": u.get("email") if u else "admin",
    }
    res = await db.online_return_actions.insert_one(doc)
    doc["_id"] = str(res.inserted_id)
    return doc

@online_returns_router.get("/actions")
async def list_applied_fixes(style_code: Optional[str] = None):
    db = get_db()
    q = {}
    if style_code:
        q["style_code"] = style_code.strip()
    cursor = db.online_return_actions.find(q).sort("applied_date", -1)
    actions = []
    async for a in cursor:
        a["_id"] = str(a["_id"])
        actions.append(a)
    return actions

@online_returns_router.get("/impact-check")
async def check_return_reduction_impact(
    request: Request,
    style_code: Optional[str] = None,
    platform: str = Query("myntra"),
):
    db = get_db()
    
    # Find applied actions
    q = {}
    if style_code and isinstance(style_code, str):
        q["style_code"] = style_code.strip()
    actions = await db.online_return_actions.find(q).to_list(100)
    
    results = []
    for act in actions:
        st = act.get("style_code")
        applied_date = act.get("applied_date")
        
        # Pre-fix returns vs post-fix returns
        pre_returns = await db.online_returns_records.count_documents({
            "platform": platform.lower(),
            "style_code": st,
            "return_date": {"$lt": applied_date}
        })
        post_returns = await db.online_returns_records.count_documents({
            "platform": platform.lower(),
            "style_code": st,
            "return_date": {"$gte": applied_date}
        })
        
        # Calculate reduction percentage
        if pre_returns > 0:
            reduction_pct = round(((pre_returns - post_returns) / pre_returns) * 100, 1)
        else:
            reduction_pct = 0.0
            
        saved_freight = max(0.0, round((pre_returns - post_returns) * 85.0, 2))
        
        status = "IN_PROGRESS"
        if pre_returns > 0:
            if reduction_pct >= 20.0:
                status = "REDUCED_SUCCESSFULLY"
            elif reduction_pct < 0:
                status = "NEEDS_FURTHER_REVISION"
                
        results.append({
            "action_id": str(act["_id"]),
            "style_code": st,
            "title": act.get("title"),
            "action_type": act.get("action_type"),
            "applied_date": applied_date,
            "pre_fix_returns": pre_returns,
            "post_fix_returns": post_returns,
            "reduction_pct": reduction_pct,
            "saved_freight": saved_freight,
            "status": status,
        })
        
    return {"results": results}
