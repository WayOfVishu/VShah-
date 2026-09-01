// Tier 1 connector: Ashby's public job-board posting API. No auth, no ToS
// issue (PRD req. 1). https://developers.ashbyhq.com/reference/jobpostingapi

const BASE = "https://api.ashbyhq.com/posting-api/job-board";

export async function probe(slug) {
  const res = await fetch(`${BASE}/${slug}`);
  if (!res.ok) return false;
  const body = await res.json();
  return Array.isArray(body.jobs) && body.jobs.length > 0;
}

export async function fetchPostings(slug) {
  const res = await fetch(`${BASE}/${slug}?includeCompensation=true`);
  if (!res.ok) {
    throw new Error(`ashby:${slug} responded ${res.status}`);
  }
  const body = await res.json();
  return (body.jobs || []).map((job) => ({ ...job, __slug: slug }));
}
