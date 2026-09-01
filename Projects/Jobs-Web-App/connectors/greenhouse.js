// Tier 1 connector: Greenhouse's public JSON board API. No auth, no ToS
// issue (PRD req. 1). https://developers.greenhouse.io/job-board.html

const BASE = "https://boards-api.greenhouse.io/v1/boards";

// Probe-only fetch used by the bootstrap script (scripts/bootstrap-sources.js)
// to test whether a company slug has a public Greenhouse board at all.
export async function probe(slug) {
  const res = await fetch(`${BASE}/${slug}/jobs`);
  if (!res.ok) return false;
  const body = await res.json();
  return Array.isArray(body.jobs) && body.jobs.length > 0;
}

// Full fetch used by discover.js: pulls postings with content for a
// known-good slug.
export async function fetchPostings(slug) {
  const res = await fetch(`${BASE}/${slug}/jobs?content=true`);
  if (!res.ok) {
    throw new Error(`greenhouse:${slug} responded ${res.status}`);
  }
  const body = await res.json();
  return (body.jobs || []).map((job) => ({ ...job, __slug: slug }));
}
