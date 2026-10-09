import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from services.supabase_invoice_service import sync_direct_invoice_to_supabase, sync_invoice_payment_to_supabase

log = logging.getLogger("erp.outbox")

async def process_outbox_events(db: Any):
    """
    Background worker that continuously polls the outbox_events collection
    and pushes pending events to Supabase.
    """
    log.info("Starting Supabase outbox processor background worker...")
    while True:
        try:
            # Find one pending event, prioritizing older ones
            event = await db.outbox_events.find_one_and_update(
                {"status": "pending"},
                {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc).isoformat()}},
                sort=[("created_at", 1)]
            )
            
            if not event:
                # No pending events, wait before polling again
                await asyncio.sleep(5)
                continue

            event_id = event["_id"]
            event_type = event.get("type")
            payload = event.get("payload")
            
            log.info(f"Processing outbox event {event_id} of type {event_type}")

            success = False
            error_msg = None

            try:
                if event_type == "direct_invoice_created":
                    res = sync_direct_invoice_to_supabase(payload)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for invoice sync.")
                elif event_type == "payment_received":
                    # payment payload needs payment_doc and invoice_docs
                    payment_doc = payload.get("payment_doc")
                    invoice_docs = payload.get("invoice_docs", [])
                    res = sync_invoice_payment_to_supabase(payment_doc, invoice_docs)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for payment sync.")
                else:
                    log.warning(f"Unknown outbox event type: {event_type}")
                    
                success = True
            except Exception as e:
                error_msg = str(e)
                log.error(f"Error processing outbox event {event_id}: {error_msg}")
                log.debug(traceback.format_exc())

            if success:
                await db.outbox_events.update_one(
                    {"_id": event_id},
                    {"$set": {
                        "status": "processed",
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
            else:
                retries = event.get("retries", 0) + 1
                new_status = "failed" if retries >= 5 else "pending"
                await db.outbox_events.update_one(
                    {"_id": event_id},
                    {"$set": {
                        "status": new_status,
                        "error": error_msg,
                        "retries": retries,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                if new_status == "failed":
                    # Optionally record in supabase_sync_failures for manual review
                    try:
                        from services.supabase_sync_failure_service import record_supabase_sync_failure
                        await record_supabase_sync_failure(db, event.get("collection", "unknown"), str(event.get("doc_id")), error_msg)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            log.info("Outbox processor worker cancelled.")
            break
        except Exception as e:
            log.error(f"Outbox processor encountered a fatal error: {e}")
            await asyncio.sleep(10)

def start_outbox_processor(db: Any):
    asyncio.create_task(process_outbox_events(db))
