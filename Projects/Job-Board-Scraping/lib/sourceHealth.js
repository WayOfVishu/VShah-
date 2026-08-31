// PRD req. 4-5, 19: tracks per-source retry_count/status so a connector that
// keeps failing surfaces as `permanent-fail` instead of silently looking
// like "no new postings today." Shared by discover.js across both tiers.

export function recordSourceSuccess(db, name) {
  db.prepare(
    `INSERT INTO sources (name, retry_count, status, last_success_at)
     VALUES (@name, 0, 'ok', datetime('now'))
     ON CONFLICT(name) DO UPDATE SET retry_count = 0, status = 'ok', last_success_at = datetime('now')`
  ).run({ name });
}

// Returns { retryCount, status } after recording the failure. Three
// consecutive failures (no intervening success) trips permanent-fail.
export function recordSourceFailure(db, name) {
  const existing = db.prepare("SELECT retry_count FROM sources WHERE name = ?").get(name);
  const retryCount = (existing?.retry_count ?? 0) + 1;
  const status = retryCount >= 3 ? "permanent-fail" : "render-failed";
  db.prepare(
    `INSERT INTO sources (name, retry_count, status)
     VALUES (@name, @retryCount, @status)
     ON CONFLICT(name) DO UPDATE SET retry_count = @retryCount, status = @status`
  ).run({ name, retryCount, status });
  return { retryCount, status };
}
