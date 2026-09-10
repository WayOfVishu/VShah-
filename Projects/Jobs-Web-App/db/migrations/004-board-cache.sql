-- Board resolution cache for the company x platform model in config/sources.json.
--
-- sources.json now names companies, not boards: a company is looked for on
-- every enabled platform so a role posted only to, say, Ashby is not missed
-- because the company was hand-filed under Greenhouse. That lookup is a
-- cross-product of probes (companies x platforms x slug candidates) and is far
-- too expensive to repeat on every run, so each answer - including a negative
-- one - is recorded here and reused until it expires.
--
-- Caching the misses matters as much as caching the hits: most cells in the
-- cross-product are misses, and without them every run would re-probe every
-- platform a company is not on.

CREATE TABLE IF NOT EXISTS board_cache (
  company     TEXT NOT NULL,
  platform    TEXT NOT NULL,
  -- The identifier the connector needs. A JSON string, because the shape is
  -- platform-specific: slug platforms store "stackadapt", Workday stores
  -- {"tenant":"bmo","host":"wd3","site":"External"}. NULL means "probed and
  -- this company has no board on this platform".
  identifier  TEXT,
  found       INTEGER NOT NULL DEFAULT 0,
  -- 'probe'    - discovered automatically by lib/boardResolver.js
  -- 'override' - taken verbatim from config/sources.json, never expires
  origin      TEXT NOT NULL DEFAULT 'probe',
  checked_at  TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (company, platform)
);

CREATE INDEX IF NOT EXISTS idx_board_cache_found ON board_cache(found);
