-- =============================================================================
-- Analog Elk v3 — Migration 003: SEO + Performance Run History
-- =============================================================================
-- Stores one row per audit run (SEO checker, perf checker, full workflow).
-- Powers trend tracking, regression detection, and competitor comparison.
-- Safe to re-run (uses CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS).
-- =============================================================================

CREATE TABLE IF NOT EXISTS seo_runs (
    id              BIGSERIAL PRIMARY KEY,
    url             TEXT NOT NULL,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- SEO scoring (from seo_checker.py); nullable for perf-only runs.
    seo_score       SMALLINT,
    issue_count     INTEGER,
    -- Performance metrics; nullable depending on which tools ran.
    ttfb_ms         REAL,
    lcp_ms          REAL,
    cls             REAL,
    inp_ms          REAL,
    fcp_ms          REAL,
    -- Page weight in KB.
    total_weight_kb REAL,
    js_kb           REAL,
    css_kb          REAL,
    image_kb        REAL,
    -- Lighthouse category scores (0–100).
    perf_score      SMALLINT,
    a11y_score      SMALLINT,
    bp_score        SMALLINT,
    -- Link audit summary.
    broken_links    INTEGER,
    -- Source data: which tools ran, full result blobs, free-form labels.
    tool_set        TEXT[]    NOT NULL DEFAULT ARRAY[]::TEXT[],
    label           TEXT      NOT NULL DEFAULT '',
    raw             JSONB     NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE seo_runs IS
    'One row per SEO/perf audit run. Used for trend tracking and regression detection.';
COMMENT ON COLUMN seo_runs.tool_set IS
    'Names of tools that contributed (e.g. {seo_checker,lighthouse,crux}).';
COMMENT ON COLUMN seo_runs.label IS
    'Free-form tag for grouping runs (e.g. "before-redesign", "client-name").';
COMMENT ON COLUMN seo_runs.raw IS
    'Full structured result for downstream re-analysis without re-running tools.';

CREATE INDEX IF NOT EXISTS idx_seo_runs_url
    ON seo_runs (url);

CREATE INDEX IF NOT EXISTS idx_seo_runs_url_run_at
    ON seo_runs (url, run_at DESC);

CREATE INDEX IF NOT EXISTS idx_seo_runs_label
    ON seo_runs (label) WHERE label <> '';

-- ---------------------------------------------------------------------------
-- Latest-per-URL view — convenience for dashboards.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW seo_runs_latest AS
SELECT DISTINCT ON (url)
    url,
    run_at,
    seo_score,
    perf_score,
    a11y_score,
    bp_score,
    issue_count,
    ttfb_ms,
    lcp_ms,
    cls,
    inp_ms,
    total_weight_kb,
    broken_links,
    tool_set,
    label
FROM seo_runs
ORDER BY url, run_at DESC;

COMMENT ON VIEW seo_runs_latest IS
    'Latest run per URL. Use for dashboards and "current state" queries.';
