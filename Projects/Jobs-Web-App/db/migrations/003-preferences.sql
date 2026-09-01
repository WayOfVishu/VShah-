-- Preference filtering + scoring (the merged Jobs-Web-App).
--
-- match_score already existed but was always NULL - no scoring logic shipped
-- in v1. These columns record how a score was arrived at, so a ranking can be
-- explained in the dashboard instead of being an opaque number, and so the
-- balanced feed can group by bucket without re-parsing location strings on
-- every request.
--
-- ADD COLUMN is not expressible as IF NOT EXISTS in SQLite; db/migrate.js
-- swallows the resulting "duplicate column name" error so a re-run stays safe.

ALTER TABLE discovered_jobs ADD COLUMN location_bucket TEXT;
ALTER TABLE discovered_jobs ADD COLUMN location_score REAL;
ALTER TABLE discovered_jobs ADD COLUMN keyword_score REAL;
ALTER TABLE discovered_jobs ADD COLUMN unsponsored_us INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_discovered_jobs_bucket ON discovered_jobs(location_bucket);
CREATE INDEX IF NOT EXISTS idx_discovered_jobs_posted ON discovered_jobs(posted_date);
