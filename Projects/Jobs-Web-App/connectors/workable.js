// Tier 1 connector: Workable's public job-board widget API. No auth.
// https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true
//
// `details=true` returns the full description inline, so unlike Workday this
// is a single request per company — no second pass for job bodies.
//
// Workable is where a lot of small Calgary shops land: it is cheap, so
// companies too small for Greenhouse and too new for Workday use it. Each one
// is only a handful of postings, which is exactly why it is worth having a
// connector rather than checking the pages by hand.

const BASE = "https://apply.workable.com/api/v1/widget/accounts";

export async function probe(slug, { throttledFetch = fetch, rateLimitMs = 1500 } = {}) {
  try {
    const res = await throttledFetch(`${BASE}/${slug}`, { headers: { accept: "application/json" } }, rateLimitMs);
    if (!res.ok) return false;
    const body = await res.json();
    return Array.isArray(body.jobs) && body.jobs.length > 0;
  } catch {
    return false;
  }
}

export async function fetchPostings(entry, { throttledFetch, rateLimitMs = 1500 } = {}) {
  const slug = entry.slug || entry;
  const res = await throttledFetch(
    `${BASE}/${slug}?details=true`,
    { headers: { accept: "application/json" } },
    rateLimitMs
  );
  if (!res.ok) {
    throw new Error(`workable:${slug} responded ${res.status}`);
  }
  const body = await res.json();
  const company = entry.name || body.name || slug;
  return (body.jobs || []).map((job) => ({ ...job, __company: company }));
}
