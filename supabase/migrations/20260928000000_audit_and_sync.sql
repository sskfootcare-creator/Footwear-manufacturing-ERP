-- ============================================================================
-- SSK FOOTWEAR ERP — AUDIT & SYNC RECONCILIATION MIGRATION (DB-003, OPS-023, DATA-024)
-- Provides persistent financial audit logging and sync failure reconciliation.
-- ============================================================================

-- 1. ERP AUDIT LOGS
CREATE TABLE IF NOT EXISTS erp_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action VARCHAR(50) NOT NULL,
    category VARCHAR(50) NOT NULL,
    details TEXT NOT NULL,
    actor_email VARCHAR(100) NOT NULL,
    request_id VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_category_date ON erp_audit_logs(category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON erp_audit_logs(actor_email);
CREATE INDEX IF NOT EXISTS idx_audit_req ON erp_audit_logs(request_id) WHERE request_id IS NOT NULL;

-- 2. SUPABASE SYNC FAILURES RECONCILIATION LOG
CREATE TABLE IF NOT EXISTS supabase_sync_failures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_id VARCHAR(100) NOT NULL,
    collection VARCHAR(100) NOT NULL,
    document_id VARCHAR(100) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    error_message TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'FAILED',
    replayed_at TIMESTAMPTZ,
    replayed_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sync_fail_status ON supabase_sync_failures(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_fail_doc ON supabase_sync_failures(collection, document_id);

-- 3. ROW LEVEL SECURITY
ALTER TABLE erp_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE supabase_sync_failures ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename IN ('erp_audit_logs', 'supabase_sync_failures')
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS rls_authenticated_access ON %I', tbl);
        EXECUTE format('CREATE POLICY rls_authenticated_access ON %I FOR ALL TO authenticated USING (true) WITH CHECK (true)', tbl);
        EXECUTE format('DROP POLICY IF EXISTS rls_service_role_access ON %I', tbl);
        EXECUTE format('CREATE POLICY rls_service_role_access ON %I FOR ALL TO service_role USING (true) WITH CHECK (true)', tbl);
    END LOOP;
END;
$$;
