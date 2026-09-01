// PRD req. 11-12: fuzzy-match postings on normalized title+company+location
// to collapse the same role cross-posted on multiple boards, plus a
// same-apply_url shortcut for exact re-runs.

import Fuse from "fuse.js";

const FUZZY_THRESHOLD = 0.2; // lower = stricter match; fuse.js scores 0 (exact) to 1 (no match)

export function dedupKey(job) {
  return [job.title, job.company, job.location || ""]
    .join(" ")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

// Builds a Fuse index over existing discovered_jobs rows for matching new
// candidates against. `existingRows` must have `apply_url` plus the fields
// dedupKey() reads (title, company, location).
export function buildDedupIndex(existingRows) {
  const indexed = existingRows.map((row) => ({ row, key: dedupKey(row) }));
  const fuse = new Fuse(indexed, { keys: ["key"], includeScore: true, threshold: FUZZY_THRESHOLD });
  return { fuse, byApplyUrl: new Map(existingRows.map((r) => [r.apply_url, r])) };
}

// Returns the existing row a candidate duplicates, or null if it's genuinely new.
export function findDuplicate(candidate, index) {
  if (index.byApplyUrl.has(candidate.apply_url)) {
    return index.byApplyUrl.get(candidate.apply_url);
  }
  const results = index.fuse.search(dedupKey(candidate));
  if (results.length > 0 && results[0].score <= FUZZY_THRESHOLD) {
    return results[0].item.row;
  }
  return null;
}

// Adds a freshly-inserted row to a live index so later candidates in the
// same run (e.g. the same job matched by two different Remotive keyword
// searches) also dedup against it, not just rows that existed at
// buildDedupIndex() time.
export function addToIndex(index, row) {
  index.byApplyUrl.set(row.apply_url, row);
  index.fuse.add({ row, key: dedupKey(row) });
}
