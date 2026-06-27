# SSK Footcare ERP — PRD

## Original Problem Statement
Build a comprehensive local/cloud B2B footwear manufacturing ERP. Costing calculation based on raw-material yield, order management against styles, production floor tracking (9 stages) with kanban-style colour×size matrix, PO upload/extraction from PDF/Excel, multi-user/multi-role login, inventory, worker payroll ledger and productivity bonuses.

## User Personas
- Admin / Owner — full system control, settings, users, costing margins
- Manager — POs, production scheduling, payroll, reports
- Production lead — daily floor (kanban, assignments, defects, WhatsApp share)
- Sales — POs, styles, dispatch invoices

## Core Requirements (static)
1. Style master with BOM + yield-based costing + image
2. PO upload from PDF/Excel with auto job creation
3. Production floor with 9 stages, colour×size matrix
4. Inventory with auto-consumption on procurement→cutting
5. Worker (Karigar) master + assignment + ledger + bonus
6. Payroll with advances + payments + ledger reconciliation
7. PDFs: Production Card (with per-process tally), Dispatch Challan, Tax Invoice, Material Requirements, Wage Slip
8. Multi-user RBAC (admin/manager/production/sales)
9. Visual reports (variance, cycle time, defect, monthly, karigar)
10. Time-bound stages with overdue alerts (admin-configurable)
11. WhatsApp share for production cards

## What's been implemented
- 2026-06-25 (forks 1-9): Full ERP base, Auth, PO PDF parsing, Production kanban (color×size), BOM/Yield costing, Style image upload, Components tracking, Karigar assignment + DnD bulk re-assign, Karigar ledger + bonus + wage-slip PDF, Inventory auto-consume + reorder alerts, Dispatch Challan + Tax Invoice + Material Req PDFs.
- 2026-06-26 (this fork — iteration 10):
  • **P0 fix**: Payment recording 400 error in Payroll (`openLedger(ledgerFor.row)`)
  • **Settings/ETA**: `/api/settings/stage-durations` + `/settings` page — admin configures per-stage hours
  • **Time-bound stages**: `stage_entered_at` + `stage_deadline` saved on every transition + initial job creation
  • **Overdue alerts**: `/api/dashboard/overdue` + red banner on Dashboard + red `OVERDUE` strip on Production cards
  • **Visual Reports** (Recharts): Production Trend (line), Karigar Output (bar), Cost Variance (bar), Cycle Time (bar), Defect Analytics (bar + pie)
  • **Production Card PDF**: added `PROCESS TALLY` table — per-process × per-size grid (DONE/REJ/SIGN columns) for floor workers to fill in
  • **WhatsApp Share**: green WhatsApp button on every production card, dialog with karigar phone picker, downloads PDF locally + opens wa.me chat

## Prioritized Backlog
**P0** — none open
**P1** — Bulk pay multiple karigars at end-of-week (deferred per user)
**P2** — Server-side WhatsApp Cloud API for direct PDF upload (no manual drag-drop)
**P2** — Visual seed for testing overdue badge (job with past stage_deadline)
**P3** — Split `server.py` into modules (production / payroll / reports)

## Next Tasks
- (When user asks) Bulk pay multi-karigar payout flow
- (When user asks) WhatsApp Cloud API integration

## Iteration 11 (2026-06-26)
- **FREE PO Extractor**: Replaced LLM-only path with `po_extractor_free.py` using `pdfplumber` + `openpyxl`. Zero recurring cost, no Cloudflare/timeout failures. LLM remains optional fallback if EMERGENT_LLM_KEY is set. Verified working on numeric (SIYARAM 2220008835) and alphabetic (TEST-PO-001) POs.
- **Packing List**: 
  • Default SSK template generator (`packing_list.py`) matching uploaded template format exactly.
  • Custom per-client templates: upload xlsx with `{{placeholders}}` like `{{po_number}}`, `{{client_name}}`, `{{vendor_gstin}}`, `{{lines}}` for the line-item row marker. Header row above `{{lines}}` is auto-detected to map columns.
  • Endpoints: `POST /api/packing-lists/job`, `GET/POST/DELETE /api/packing-templates`.
- **Auto-archive**: Once a job has BOTH `invoice_generated_at` and `packing_generated_at` set, it gets `archived=True`. `GET /api/production/jobs` filters out archived (use `?include_archived=true` to include).
- **Archive UI** (`Production.jsx`): "Archive (N)" toggle button → `ArchivePanel` showing grouped archived cards with style image, PO info, sizes, three actions (View Details / Card PDF / Packing). `DetailModal` shows full size breakdown, karigar assignments, and stage history table.
- **A4 Production Card fix** (`pdf_card.py`): Total width capped at 180mm usable. Company name strip now WHITE on dark background (was black-on-dark = invisible). Tally + size columns scale to fit. Tested with 9 sizes → all columns fit on A4.

### Verified
- iteration_11.json: Backend 7/7, Frontend 4/4 critical flows green. Auto-archive end-to-end (PATCH dispatched → POST invoice → POST packing → archived=True). PDF page size exactly 595x842 pt with 'SSK FOOTCARE MANUFACTURING LLP' string present.

## Iteration 12 (2026-06-26)
- **PDF Extractor fix for SHEIN/NEXTGEN format**: multi-line table cells, comma-split description → desc/color/size, smarter client/vendor detection (top-of-document and Vendor-Code pattern), Total Order Value / TOTALBASICVALUE detection, prefer BaseCost over MRP for unit_price. Verified: 126 line items from 25-page PDF.
- **Packing-list manual fields**: dispatch_date, transporter, vehicle_no, driver_name, driver_phone, site_code, destination, port, notes all captured via a modal and rendered into the xlsx (row 15 + notes block at bottom).
- **Persistence & re-download**: every generated packing list saved (file_b64 in `packing_lists`). `GET /api/packing-lists` lists them, `GET /api/packing-lists/{id}/file` re-downloads the exact original bytes. Archive view shows a "Saved Packing Lists" table.
- **Merged packing list**: `POST /api/packing-lists/merged` produces ONE xlsx for jobs spanning multiple POs of the same client. Optional `sectioned=true` inserts a "PO: <number>" header row per source PO. Cross-client merges 400.
- **Auto-pick template by alias**: `PackingTemplate.aliases: List[str]`. When generating without explicit `template_id`, the system picks the template whose alias is a case-insensitive substring of the PO's client_name. Settings page exposes upload/list/delete UI.
- **UI Polish**: `Card` component now forwards arbitrary props (data-testid, style, etc.) — fixes the LOW-priority pass-through issues flagged in test report.

### Verified (iteration_12.json)
- Backend: 10/10
- Frontend: all 4 critical flows green (Packing modal with 14 fields, Merge-Packing button, Archive view re-download, Templates upload+delete)

## Iteration 13 (2026-06-27) — Accounts Receivable / Tally Ledger
**Complete AR / Receivables system:**
- **Invoice archive**: All generated invoices saved with PDF bytes (`file_b64`) + due_date (default +45d, override from PO payment_terms numeric) + computed totals (subtotal, CGST/SGST/IGST, grand_total). Page `/invoices` with 5 status tiles (Total / Pending / Partial / Overdue / Paid), search, status filters, row actions (view detail, download PDF, record GRN, record payment). Re-download via `/api/invoices/{id}/file`.
- **GRN (Goods Receipts)**: `POST /api/grns` — line-item level capture of dispatched / received / accepted / rejected qty with rejection_reason. Auto-numbered `GRN-2026-NNNN`. Short / rejected pcs auto-reduce the invoice's net amount via `grn_adjustment`.
- **Payments**: `POST /api/payments` — FIFO-allocates a lump-sum across selected invoices by due_date. Modes: Bank Transfer/RTGS/NEFT/Cheque/UPI/Cash/Adjustment. Captures reference (UTR/Cheque#), bank, notes. Over-payments record `advance_amount`. Auto-numbered `RCT-2026-NNNN`.
- **Tally-style Client Ledger**: `GET /api/clients` + `/api/clients/{name}/ledger`. Returns chronological entries with vch_type (Invoice/Payment/GR Adj), Dr/Cr columns, running balance with Dr/Cr suffix, closing balance, aging buckets [0-30, 31-60, 61-90, 90+], totals.
- **Overdue alert**: Dashboard red banner when any invoice past its due_date; Invoices page red tile.
- **Legacy clean-up**: 12 pre-AR invoices flagged `legacy: True` and excluded from listing by default (toggleable via `?include_legacy=true`).

### Verified (iteration_13.json)
- Backend: 19/19 pytest passed
- Frontend: 100% (all critical flows verified: Invoices list, modal, GRN dialog, Payment dialog, Clients list, Tally Ledger modal with aging)
