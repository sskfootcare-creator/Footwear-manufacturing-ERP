# Online Commerce Fix Report

## Fixed issues
1. OC-001: Added normalized `platform_key`, `order_id_key`, and `line_id_key` handling in configured online order imports. Duplicate orders and order lines are now skipped/reported instead of blindly inserted.
2. OC-002: Hardened pick confirmation by rejecting closed picklists, atomically claiming the item before stock effects, and requiring the exact WMS location to have both physical and reserved stock before deduction.
3. OC-003: Added normalized marketplace/SKU/style/color key fields for SKU maps and marketplace style-color mappings, plus startup unique indexes over those normalized identities.

## Unfixed issues
- OC-004 settlement/daily/monthly import idempotency remains a verified high-risk gap because the authoritative row identity varies by platform and must be validated against real source files before adding uniqueness constraints.
- OC-005 B2B-vs-online allocation policy remains NOT VERIFIED / BUSINESS RULE NOT IMPLEMENTED. No policy was invented.

## Files changed
- `backend/server.py`
- `backend/tests/test_online_commerce_guards.py`
- `ONLINE_COMMERCE_AUDIT.md`
- `ONLINE_COMMERCE_FIX_REPORT.md`
- `ONLINE_COMMERCE_TEST_REPORT.md`

## Database changes
- New normalized fields on newly written `sku_map`, `marketplace_style_color_mapping`, `online_orders`, and `online_order_items` documents.
- New startup indexes: normalized unique SKU map, normalized unique marketplace style-color mapping, configured online order unique identity, configured online order-line unique identity.

## Migration requirements
- Backfill normalized key fields for existing documents before relying on the new indexes in production.
- Deduplicate historical records that collide after trimming/case-folding before creating unique indexes.
