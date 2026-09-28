# Architecture Decision Record (ADR-001): Dual-Database Architecture & Systems of Record

**Status:** APPROVED  
**Date:** 2026-09-28  
**Audit Reference:** ARCH-001, ARCH-019, DB-005, OPS-023  
**Deciders:** Lead Architect, Core Platform Team  

---

## 1. Context & Problem Statement
The SSK Footwear Manufacturing ERP system previously utilized MongoDB for operational activities (manufacturing execution, shopfloor jobs, WMS barcode scans, catalog SKU mapping) and synchronized selected sales invoices, purchases, and bank entries into Supabase (PostgreSQL).

Operating two databases without an explicit System of Record (SoR) boundary created eventual-consistency risks, ambiguous transaction ownership, potential duplicate records during retries, and manual reconciliation overhead.

---

## 2. Decision: Bounded Domain System of Record (SoR)

To eliminate split-brain state and guarantee financial integrity, each business domain is assigned exactly **one authoritative System of Record**:

| Domain / Bounded Context | Authoritative Database | Secondary / Read Projection | Sync Direction & Mechanism |
| :--- | :--- | :--- | :--- |
| **Financial General Ledger, Chart of Accounts, Double-Entry JEs** | **PostgreSQL (Supabase)** | None (Strictly Authoritative) | Writes only originate from financial services |
| **Official Sales Invoices, Vendor Bills, GST & Payments** | **PostgreSQL (Supabase)** | MongoDB (operational cache) | Outbox / Idempotent Sync (`supabase_invoice_service`, `supabase_vendor_bill_service`) |
| **Manufacturing Execution (Shopfloor, Jobs, Workers, Karigar Tasks)** | **MongoDB** | Supabase (Payroll Journal Entry) | MongoDB Primary; completed wage disbursements sync to Supabase Journal Lines |
| **Physical WMS & Barcode Scanning (Racks, Locations, Offline Batches)** | **MongoDB** | None | Pure operational execution in MongoDB |
| **Marketplace SKU Mapping & Online Order Ingestion** | **MongoDB** | Supabase (Settlement JE) | Ingested into MongoDB; settlement imports post balanced journal entries to Supabase |

---

## 3. Conflict Handling, Idempotency & Deterministic Keys
1. **Deterministic UUIDs**: Cross-database synchronization uses deterministic UUIDs generated via `uuid.uuid5(uuid.NAMESPACE_OID, f"{entity_type}_{source_id}")`.
2. **Immutable Financial Journal Entries**: Every journal entry requires strict balancing (`total_debit == total_credit`), verified by Python services and enforced by database check constraint `chk_balanced_entry`.
3. **Double-Entry Reversal**: Posted journal entries in Supabase are immutable. Any error or void action creates an offsetting reversal journal entry with explicit audit tracking.

---

## 4. Failure Handling & Retry Policy
1. **Persistence of Sync Failures**: When synchronization from MongoDB to Supabase fails due to temporary network or connection issues, the event is immediately captured in MongoDB's `supabase_sync_failures` collection and Supabase's `supabase_sync_failures` table.
2. **Replayability**: The endpoint `/api/supabase/replay-sync-failures` and CLI runners can safely replay failed transactions without side effects or duplicates.
3. **Circuit Breaker & Fallback**: Offline mobile clients buffer scans locally and submit batches with `client_sync_id` and `op_id`. Deduplication against `offline_operation_registry` guarantees repeat syncs are no-ops.

---

## 5. Automated Reconciliation Jobs
1. **Nightly Invariant Checks**: Automated scheduled tasks compare:
   - Invoices in MongoDB vs `sales_invoices` in Supabase.
   - Payments recorded vs `payment_vouchers` and `bank_statement_lines`.
2. **Variance Reporting**: The Reconciliation Engine flags any discrepancy between operational invoice totals and financial sub-ledger balances, targeting **0 unexplained differences**.
