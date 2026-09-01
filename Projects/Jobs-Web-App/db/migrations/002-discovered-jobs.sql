-- PRD req. 17-19: discovered-jobs pipeline tables.
-- Applied via db/migrate.js; additive only, never touches the existing
-- `jobs` table.

CREATE TABLE IF NOT EXISTS discovered_jobs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id          TEXT NOT NULL,               -- source-native id, for traceability
  sources         TEXT NOT NULL,               -- JSON array of source names, e.g. ["greenhouse","lever"]
  title           TEXT NOT NULL,
  company         TEXT NOT NULL,
  location        TEXT,
  salary          TEXT,
  description     TEXT,
  apply_url       TEXT NOT NULL,               -- canonical apply link (first source seen)
  posted_date     TEXT,
  remote_status   TEXT,
  first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
  status          TEXT NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new','queued','generating','tailored','rejected','dismissed','applied','archived')),
  resume_path     TEXT,
  match_score     REAL,                        -- nullable; no scoring logic ships in v1 (PRD Open Questions)
  applied_job_id  INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
  tailor_error    TEXT                          -- last error message on generating -> queued fallback (req. 28)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_discovered_jobs_apply_url ON discovered_jobs(apply_url);
CREATE INDEX IF NOT EXISTS idx_discovered_jobs_sort ON discovered_jobs(match_score, first_seen_at);
CREATE INDEX IF NOT EXISTS idx_discovered_jobs_status ON discovered_jobs(status);

CREATE TABLE IF NOT EXISTS sources (
  name            TEXT PRIMARY KEY,
  retry_count     INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'ok'
                  CHECK (status IN ('ok','render-failed','permanent-fail')),
  last_success_at TEXT
);

CREATE TABLE IF NOT EXISTS overrides (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  discovered_job_id  INTEGER NOT NULL REFERENCES discovered_jobs(id) ON DELETE CASCADE,
  flagged_text       TEXT NOT NULL,
  reason             TEXT NOT NULL,
  timestamp          TEXT NOT NULL DEFAULT (datetime('now'))
);
