# Online Commerce Audit

Audit date: 2026-08-11
Repository: Footwear-manufacturing-ERP

## Scope inspected
- Frontend pages requested by the audit: `OnlineOrders.jsx`, `OnlineProfitability.jsx`, `OnlineStylePipeline.jsx`, `OrderImportFormats.jsx`, `SkuMap.jsx`, `Picklists.jsx`, `ReadyStock.jsx`, `WarehouseDashboard.jsx`, and `WarehouseReports.jsx`.
- Backend models requested by the audit: `sku_map.py`, `orders.py`, `inventory.py`, `wms.py`, and `online_reconciliation.py`.
- Backend implementation: `backend/server.py`, especially SKU mapping/resolution, configured imports, legacy online imports, WMS location inventory, picklists, dispatch imports, monthly report imports, settlements, reconciliation, profitability, and index creation.
- Existing tests related to SKU, unmapped sizes, direct resolution, GST import warnings, and online reconciliation.

## Verified data flow summary
MARKETPLACE FILE/API -> order import endpoints (`/api/online-orders/import`, `/api/online-orders/import-configured`, `/api/online-orders/dispatch-import`, `/api/online-orders/monthly-report-import`, `/api/online-orders/settlement-import`) -> row parsing and validation -> SKU/style/color/size resolution (`resolve_style`, `_resolve_marketplace_sku`) -> WMS stock checks (`fg_location_inventory`) -> order/job persistence (`online_orders`, `online_order_items`, `production_jobs`) -> picklist generation (`picklists`) -> picking (`/api/picklists/{pid}/pick-item`) -> FG movements (`fg_stock_movements`, `fg_inventory`) -> reconciliation/profitability (`online_*` collections and cost snapshots).

## Issue OC-001
- Severity: CRITICAL
- Business Risk: Duplicate marketplace order imports could create duplicate business orders/items, duplicate fulfillment work, and incorrect reconciliation/profitability.
- Exact File: `backend/server.py`
- Exact Function / Component: `import_online_orders_configured`
- API Endpoint: `POST /api/online-orders/import-configured`
- Database Collection: `online_orders`, `online_order_items`
- Current Logic: The commit path inserted every grouped order and every item unconditionally.
- Observed Problem: Uploading the same configured order file twice or retrying a commit could create another `online_orders` document and item rows for the same marketplace order/line.
- Reproduction Steps: Configure a platform order import, submit the same file twice with `dry_run=false`.
- Expected Behavior: Existing order and line identities are detected and skipped idempotently.
- Actual Behavior: No normalized unique identity was applied in the commit path.
- Root Cause: Missing normalized identity fields and DB-level unique constraints for configured online order imports.
- Recommended Fix: Add normalized platform/order/line keys, skip duplicates, and create unique Mongo indexes.
- Test Required: Duplicate order import, duplicate order line, import retry.
- Migration Required: Before enabling the new unique indexes on existing production data, deduplicate historical `online_orders`/`online_order_items` that would share the same normalized keys.

## Issue OC-002
- Severity: CRITICAL
- Business Risk: Race conditions during picking could double-consume the same stock or pick a completed/cancelled picklist.
- Exact File: `backend/server.py`
- Exact Function / Component: `pick_item`, `_deduct_from_specific_location`
- API Endpoint: `POST /api/picklists/{pid}/pick-item`
- Database Collection: `picklists`, `fg_location_inventory`, `fg_inventory`, `fg_stock_movements`
- Current Logic: The backend read the picklist/item, checked `picked`, deducted location stock, then marked the item picked.
- Observed Problem: Two simultaneous requests could both pass the pre-check before either update. The location deduction also accepted unreserved stock because it only required physical `qty`.
- Reproduction Steps: Send concurrent pick confirmations for the same item; or attempt picking a line with physical stock but no location reservation.
- Expected Behavior: Only one request can claim the item; picking requires reserved stock for that exact location.
- Actual Behavior: Checks were not atomic and did not require location reservation.
- Root Cause: Non-atomic read/check/update sequence and non-conditional location deduction.
- Recommended Fix: Atomically claim the picklist item before deduction and condition location deduction on both `qty >= need` and `reserved_qty >= need`.
- Test Required: Duplicate pick, concurrent stock allocation, wrong warehouse location, insufficient reserved stock.
- Migration Required: None, but existing location rows with inconsistent `reserved_qty` should be reviewed.

## Issue OC-003
- Severity: HIGH
- Business Risk: Same marketplace SKU or marketplace style/color could map ambiguously if casing or leading/trailing spaces differ, causing wrong SKU resolution.
- Exact File: `backend/server.py`
- Exact Function / Component: `create_sku_map`, `resolve_style`, `upsert_marketplace_mapping`, `_resolve_marketplace_sku`, startup indexes
- API Endpoint: `POST /api/sku-map`, `GET /api/sku-map/resolve`, `POST /api/marketplace/style-color-mapping`, `POST /api/marketplace/parse-sku`
- Database Collection: `sku_map`, `marketplace_style_color_mapping`
- Current Logic: Runtime lookup used regex case-insensitive matching, but unique indexes were case-sensitive on raw fields.
- Observed Problem: `Flipkart / SKU1` and `flipkart / sku1` could coexist at DB level, making resolution dependent on whichever document Mongo returned.
- Reproduction Steps: Create two mappings differing only by case/spacing.
- Expected Behavior: The second mapping is rejected as a duplicate normalized identity.
- Actual Behavior: Raw unique indexes did not enforce normalized uniqueness.
- Root Cause: No canonical key fields in mapping documents/indexes.
- Recommended Fix: Store normalized key fields and enforce unique indexes over them.
- Test Required: Duplicate SKU mapping, same style/different color, same style/different size, leading/trailing spaces, upper/lower case.
- Migration Required: Existing duplicate normalized mappings must be resolved before index creation succeeds.

## Issue OC-004
- Severity: HIGH
- Business Risk: Settlement and daily payment imports can be retried and duplicated, affecting reconciliation and marketplace profitability.
- Exact File: `backend/server.py`
- Exact Function / Component: `import_settlements`, `import_daily_payments`, `import_monthly_report`
- API Endpoint: `/api/online-reconciliation/import-*`, `/api/online-orders/settlement-import`, `/api/online-orders/monthly-report-import`
- Database Collection: `online_settlements_detailed`, `online_daily_payments`, `online_monthly_order_reports`, `online_settlements`
- Current Logic: Multiple import paths insert rows without a verified DB-level idempotency key.
- Observed Problem: Duplicate settlement files or same NEFT/order rows can inflate charges/revenue.
- Reproduction Steps: Import the same settlement file twice.
- Expected Behavior: Duplicate settlement rows are skipped or reported.
- Actual Behavior: NOT FULLY FIXED in this pass; documented risk remains.
- Root Cause: Missing authoritative platform-specific settlement row identity.
- Recommended Fix: Define per-platform settlement identity from real files, add row-level duplicate reporting and unique indexes.
- Test Required: Duplicate settlement, partial settlement, same NEFT reference, unknown order.
- Migration Required: Likely after field identity is confirmed from real settlement files.

## Issue OC-005
- Severity: MEDIUM
- Business Risk: `force_negative_stock` is allowed in production/ready-stock paths and can produce negative component stock when explicitly forced; online sellable stock must remain based on positive WMS free stock.
- Exact File: `backend/server.py`
- Exact Function / Component: `produce_cell`, `_sync_warehouse_locations`, online stock checks
- API Endpoint: production cell/ready-stock endpoints using `ProduceCellIn`
- Database Collection: `fg_inventory`, `fg_location_inventory`, `component_master`, `component_stock_movements`
- Current Logic: Force-negative is an explicit override for production/component shortage workflows.
- Observed Problem: Online stock checks use WMS positive `qty - reserved_qty`, which limits propagation, but broader business allocation policy for B2B-vs-online committed stock is NOT VERIFIED.
- Reproduction Steps: Produce/adjust with forced negative components, then inspect online sellable stock calculations.
- Expected Behavior: Online orders never sell stock that does not exist.
- Actual Behavior: WMS free-stock checks protect the inspected import/picklist paths; B2B allocation policy is BUSINESS RULE NOT IMPLEMENTED / NOT VERIFIED.
- Root Cause: No documented allocation policy between B2B and online commitments.
- Recommended Fix: Keep online sellable stock tied to positive WMS free stock; define B2B/online allocation policy before further changes.
- Test Required: Negative stock, B2B allocation vs online sellable stock.
- Migration Required: None.
