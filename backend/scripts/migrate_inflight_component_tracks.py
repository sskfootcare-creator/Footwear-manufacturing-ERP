"""
migrate_inflight_component_tracks.py

Stage 6 Migration Script for Component-Aware Production Kanban.
Derives component_specs and initializes component_tracks for jobs lacking them,
converting legacy components booleans and respecting current stage progression.

Usage:
  python backend/scripts/migrate_inflight_component_tracks.py            # Dry-run mode
  python backend/scripts/migrate_inflight_component_tracks.py --apply    # Execute migration
  python backend/scripts/migrate_inflight_component_tracks.py --all      # Include completed/dispatched jobs
"""

import os
import sys
import argparse
import asyncio
import json
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

# Add backend directory to sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services.component_spec_service import (
    derive_component_specs,
    init_component_tracks,
    MERGE_GATES,
)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ssk_footwear_erp")

TERMINAL_STAGES = {"dispatched", "delivered", "closed", "cancelled"}

POST_LASTING_STAGES = {
    "lasting",
    "assembly",
    "sole_pasting",
    "finishing",
    "qc_pack",
    "dispatched",
    "delivered",
    "closed",
}

POST_SOLE_PASTING_STAGES = {
    "finishing",
    "qc_pack",
    "dispatched",
    "delivered",
    "closed",
}


def build_tracks_for_job(job_doc, component_specs):
    """
    Build updated component_tracks for a job using its legacy booleans,
    its current stage, and its component_specs.
    """
    tracks = init_component_tracks(component_specs)
    comps = component_specs.get("components", {})
    ft = component_specs.get("footwear_type", "flat")
    job_qty = job_doc.get("quantity") or 0
    current_stage = (job_doc.get("stage") or "").lower()
    legacy_comps = job_doc.get("components") or {}

    upper_done = legacy_comps.get("upper_done", False) or (current_stage in POST_LASTING_STAGES)
    bottom_done = legacy_comps.get("bottom_done", False) or (current_stage in POST_LASTING_STAGES)
    sole_done = legacy_comps.get("sole_done", False) or (current_stage in POST_SOLE_PASTING_STAGES)

    # Upper track
    if upper_done and "upper" in tracks:
        upper_stages = comps.get("upper", {}).get("stages", [])
        tracks["upper"] = {
            "status": "ready",
            "current_stage": "ready",
            "stages_completed": list(upper_stages),
            "completed_qty": job_qty,
        }

    # Bottom track
    if bottom_done and "bottom" in tracks:
        bottom_stages = comps.get("bottom", {}).get("stages", [])
        tracks["bottom"] = {
            "status": "ready",
            "current_stage": "ready",
            "stages_completed": list(bottom_stages),
            "completed_qty": job_qty,
        }

    # Sole track
    if sole_done and "sole" in tracks:
        sole_stages = comps.get("sole", {}).get("stages", [])
        tracks["sole"] = {
            "status": "ready",
            "current_stage": "ready",
            "stages_completed": list(sole_stages),
            "completed_qty": job_qty,
        }

    # Heel / Gola track
    if "heel_gola" in tracks:
        if sole_done or current_stage in POST_SOLE_PASTING_STAGES:
            heel_stages = comps.get("heel_gola", {}).get("stages", [])
            tracks["heel_gola"] = {
                "status": "ready",
                "current_stage": "ready",
                "stages_completed": list(heel_stages),
                "completed_qty": job_qty,
            }

    dual_write_components = {
        "upper_done": tracks.get("upper", {}).get("status") == "ready",
        "bottom_done": tracks.get("bottom", {}).get("status") == "ready",
        "sole_done": tracks.get("sole", {}).get("status") == "ready",
    }

    return tracks, dual_write_components


async def run_migration(apply=False, include_all=False, sample_count=3):
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DATABASE_NAME]

    print(f"Connected to database: {DATABASE_NAME}")
    print(f"Mode: {'APPLY (Database will be updated)' if apply else 'DRY RUN (Read-only)'}")
    print(f"Scope: {'All jobs' if include_all else 'In-flight jobs only (excluding dispatched/delivered/closed)'}\n")

    # Load all styles into memory
    styles_cursor = db.styles.find({})
    styles_list = await styles_cursor.to_list(10000)
    styles_by_code = {s.get("code"): s for s in styles_list if s.get("code")}
    styles_by_id = {str(s.get("_id")): s for s in styles_list if s.get("_id")}

    # Load all materials into memory
    mats_cursor = db.materials.find({})
    mats_list = await mats_cursor.to_list(10000)
    materials_by_id = {str(m.get("_id")): m for m in mats_list if m.get("_id")}
    # Also index by material code
    for m in mats_list:
        if m.get("code"):
            materials_by_id[m.get("code")] = m

    query = {}
    if not include_all:
        query["stage"] = {"$nin": list(TERMINAL_STAGES)}

    jobs = await db.production_jobs.find(query).to_list(20000)
    total_jobs = len(jobs)
    print(f"Found {total_jobs} candidate jobs matching scope.")

    needs_migration = []
    already_migrated = 0

    for job in jobs:
        has_tracks = bool(job.get("component_tracks"))
        has_specs = bool(job.get("component_specs"))
        if has_tracks and has_specs:
            already_migrated += 1
        else:
            needs_migration.append(job)

    print(f"  - Already migrated: {already_migrated}")
    print(f"  - Needing migration: {len(needs_migration)}\n")

    if not needs_migration:
        print("No jobs require migration. Everything is up to date!")
        return

    # Process and build migrations
    updates = []
    samples = []

    for idx, job in enumerate(needs_migration):
        style_doc = None
        if job.get("style_code") and job.get("style_code") in styles_by_code:
            style_doc = styles_by_code[job["style_code"]]
        elif job.get("style_id") and str(job.get("style_id")) in styles_by_id:
            style_doc = styles_by_id[str(job["style_id"])]

        color_val = job.get("color")
        color_str = color_val if isinstance(color_val, str) else None

        specs = derive_component_specs(style_doc, color=color_str, materials_by_id=materials_by_id)
        tracks, dual_write_components = build_tracks_for_job(job, specs)

        updates.append({
            "job_id": job["_id"],
            "po_number": job.get("po_number"),
            "style_code": job.get("style_code"),
            "stage": job.get("stage"),
            "specs": specs,
            "tracks": tracks,
            "components": dual_write_components,
        })

        if len(samples) < sample_count:
            samples.append({
                "job_id": str(job["_id"]),
                "po_number": job.get("po_number"),
                "style_code": job.get("style_code"),
                "stage": job.get("stage"),
                "legacy_components": job.get("components"),
                "derived_footwear_type": specs.get("footwear_type"),
                "migrated_tracks": tracks,
                "dual_write_components": dual_write_components,
            })

    print(f"=== Sample Migrations ({len(samples)} samples) ===")
    for i, s in enumerate(samples, 1):
        print(f"\n--- Sample {i} [PO: {s['po_number']} | Style: {s['style_code']} | Stage: {s['stage']}] ---")
        print(f"Job ID: {s['job_id']}")
        print(f"Footwear Type: {s['derived_footwear_type']}")
        print(f"Before (legacy booleans): {s['legacy_components']}")
        print(f"After (component_tracks): {json.dumps(s['migrated_tracks'], indent=2)}")
        print(f"Dual-write components: {s['dual_write_components']}")

    print("\n" + "=" * 50)

    if not apply:
        print(f"\n[DRY RUN COMPLETE] {len(updates)} jobs evaluated. No changes were written to MongoDB.")
        print("To apply this migration, run:")
        print("  python backend/scripts/migrate_inflight_component_tracks.py --apply")
        if not include_all:
            print("To include all historical jobs as well, add '--all'.")
        return len(updates)

    print(f"\nApplying migration to {len(updates)} jobs in MongoDB...")
    modified_count = 0
    now = datetime.now(timezone.utc).isoformat()

    for u in updates:
        res = await db.production_jobs.update_one(
            {"_id": u["job_id"]},
            {
                "$set": {
                    "component_specs": u["specs"],
                    "component_tracks": u["tracks"],
                    "components": u["components"],
                    "component_migration_at": now,
                }
            }
        )
        if res.modified_count > 0:
            modified_count += 1

    print(f"SUCCESS: Successfully migrated {modified_count} jobs in MongoDB!")
    return modified_count


def main():
    parser = argparse.ArgumentParser(description="Migrate in-flight production jobs to component tracks")
    parser.add_argument("--apply", action="store_true", help="Apply updates to MongoDB (default is dry-run)")
    parser.add_argument("--all", action="store_true", help="Migrate all jobs, including terminal dispatched/delivered/closed")
    parser.add_argument("--sample-count", type=int, default=3, help="Number of sample conversions to display")
    args = parser.parse_args()

    asyncio.run(run_migration(apply=args.apply, include_all=args.all, sample_count=args.sample_count))


if __name__ == "__main__":
    main()
