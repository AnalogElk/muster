-- =============================================================================
-- Analog Elk v3 — Migration 002: v3 Optimisations
-- =============================================================================
-- Adds compound FTS indexes for higher-recall hybrid search and a domain-level
-- stats view used by elk-engine status and /elk-status.
-- Safe to run multiple times (uses CREATE OR REPLACE / IF NOT EXISTS).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Additional FTS indexes on documents
-- ---------------------------------------------------------------------------

-- Title-only FTS — lets the RAG API boost title matches independently
CREATE INDEX IF NOT EXISTS idx_documents_title_fts
    ON documents
    USING gin(to_tsvector('english', title));

-- Combined title + content FTS — single-pass high-recall search
CREATE INDEX IF NOT EXISTS idx_documents_combined_fts
    ON documents
    USING gin(to_tsvector('english', title || ' ' || content));

-- ---------------------------------------------------------------------------
-- Domain-level statistics view
-- Used by:
--   ./bin/elk-engine status  → shows doc counts per domain
--   /elk-status command      → dashboard display
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW kb_stats AS
SELECT
    domain,
    COUNT(*)                AS doc_count,
    MAX(ingested_at)        AS last_indexed,
    MIN(ingested_at)        AS first_indexed
FROM documents
GROUP BY domain;

COMMENT ON VIEW kb_stats IS
    'Aggregate document counts and index timestamps per knowledge domain.';

-- ---------------------------------------------------------------------------
-- Source-type breakdown view
-- Useful for auditing which ingestion pipelines have run.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW kb_source_stats AS
SELECT
    source_type,
    domain,
    COUNT(*)                AS doc_count,
    MAX(ingested_at)        AS last_ingested
FROM documents
GROUP BY source_type, domain
ORDER BY source_type, domain;

COMMENT ON VIEW kb_source_stats IS
    'Document counts broken down by source_type and domain — useful for ingestion audits.';

-- ---------------------------------------------------------------------------
-- Recent documents view
-- Quick access to the last 100 ingested items for debugging.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW kb_recent AS
SELECT
    id,
    title,
    domain,
    source_type,
    source_url,
    ingested_at
FROM documents
ORDER BY ingested_at DESC
LIMIT 100;

COMMENT ON VIEW kb_recent IS
    'Last 100 ingested documents ordered by ingestion time — debugging convenience view.';
