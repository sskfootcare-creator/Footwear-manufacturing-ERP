# Online Commerce Fix Report

## Fixed issues
1. OC-001: Added normalized `platform_key`, `order_id_key`, and `line_id_key` handling in configured online order imports. Duplicate orders and order lines are now skipped/reported instead of blindly inserted.
2. OC-002: Hardened pick confirmation by rejecting closed picklists, atomically claiming the item before stock effects, and requiring the exact WMS location to have both physical and reserved stock before deduction.
3. OC-003: Added normalized marketplace/SKU/style/color key fields for SKU maps and marketplace style-color mappings, plus startup unique indexes over those normalized identities.
4. OC-004: `import_settlement` (the configured-import settlement endpoint) now computes a per-row SHA-256 idempotency key (`settlement_row_key`) from `platform:payment_id:order_ref:leaf_sku:settlement_date` and uses `update_one / $setOnInsert / upsert=True` instead of `insert_many`. Re-importing the same settlement file is fully idempotent. The response now also includes `skipped_duplicates` count. Note: `import_settlements` (reconciliation endpoint, `online_settlements_detailed`) and `import_daily_payments` already had their own row-hash / candidate-key deduplication guards; `import_monthly_reconciliation_report` already used row_hash — only the configured settlement path was missing the guard.

## Unfixed issues
- OC-005 B2B-vs-online allocation policy remains NOT VERIFIED / BUSINESS RULE NOT IMPLEMENTED. No policy was invented.

## Files changed
- `backend/routes/online_orders.py` (OC-004: settlement idempotency)
- `backend/tests/test_online_commerce_guards.py` (8 new OC-004 tests added)
- `ONLINE_COMMERCE_AUDIT.md`
- `ONLINE_COMMERCE_FIX_REPORT.md`
- `ONLINE_COMMERCE_TEST_REPORT.md`

## Database changes
- New normalized fields on newly written `sku_map`, `marketplace_style_color_mapping`, `online_orders`, and `online_order_items` documents (OC-001/003).
- New startup indexes: normalized unique SKU map, normalized unique marketplace style-color mapping, configured online order unique identity, configured online order-line unique identity (OC-001/003).
- OC-004: `online_settlements` collection now has `settlement_row_key` (SHA-256 hash) written on every new row inserted via `import_settlement`. A sparse unique index on this field should be added in production to enforce the constraint at the DB level.

## Migration requirements
- Backfill normalized key fields for existing documents before relying on the new indexes in production.
- Deduplicate historical records that collide after trimming/case-folding before creating unique indexes.
- OC-004: Existing `online_settlements` rows from the old `insert_many` path do not have `settlement_row_key`. Backfill with a migration script using the same hash formula before adding the unique index.
