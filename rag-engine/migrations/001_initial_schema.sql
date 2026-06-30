-- =============================================================================
-- Analog Elk v3 — Migration 001: Initial Schema
-- =============================================================================
-- Creates the core knowledge base tables and search indexes.
-- Safe to run multiple times (uses IF NOT EXISTS throughout).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Documents table
-- Primary store for all ingested knowledge base content.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(500)                    NOT NULL,
    content         TEXT                            NOT NULL,
    source_url      VARCHAR(1000),
    source_type     VARCHAR(100)                    DEFAULT 'manual',
    domain          VARCHAR(100),
    category        VARCHAR(200),
    tags            TEXT[],
    ingested_at     TIMESTAMP WITH TIME ZONE        DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE        DEFAULT NOW()
);

COMMENT ON TABLE documents IS
    'Primary knowledge base — all ingested documents from indexed sources and manual uploads.';

COMMENT ON COLUMN documents.source_type IS
    'Origin type: manual | schema-org | a-list-apart | directus | netlify | nextjs | react | google-seo';

COMMENT ON COLUMN documents.domain IS
    'Top-level knowledge domain matching manifest.yaml domain keys.';

COMMENT ON COLUMN documents.tags IS
    'Free-form tags for ad-hoc filtering and grouping.';

-- ---------------------------------------------------------------------------
-- Full-text search indexes on documents
-- ---------------------------------------------------------------------------

-- Primary content FTS (used by most search queries)
CREATE INDEX IF NOT EXISTS idx_documents_fts
    ON documents
    USING gin(to_tsvector('english', content));

-- Filtering indexes
CREATE INDEX IF NOT EXISTS idx_documents_domain
    ON documents(domain);

CREATE INDEX IF NOT EXISTS idx_documents_source_type
    ON documents(source_type);

CREATE INDEX IF NOT EXISTS idx_documents_source_url
    ON documents(source_url);

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- Keeps updated_at current whenever a row is modified.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Knowledge docs table
-- Structured content store — richer metadata, used for curated docs.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_docs (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(500)                NOT NULL,
    content     TEXT                        NOT NULL,
    source_url  VARCHAR(1000),
    category    VARCHAR(200),
    tags        TEXT[],
    created_at  TIMESTAMP WITH TIME ZONE    DEFAULT NOW()
);

COMMENT ON TABLE knowledge_docs IS
    'Structured curated documents with explicit categorisation. Complements the documents table.';

-- Full-text and filter indexes on knowledge_docs
CREATE INDEX IF NOT EXISTS idx_knowledge_docs_fts
    ON knowledge_docs
    USING gin(to_tsvector('english', content));

CREATE INDEX IF NOT EXISTS idx_knowledge_docs_category
    ON knowledge_docs(category);
