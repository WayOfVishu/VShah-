// Tier 2 connector: Remotive's public JSON API, keyword-searched (PRD req. 2).
// https://remotive.com/api/remote-jobs — no auth. Remotive's API terms ask
// that results link back and credit Remotive; apply_url already does that.

const BASE = "https://remotive.com/api/remote-jobs";

export async function fetchPostings(keyword, { throttledFetch, rateLimitMs }) {
  const url = `${BASE}?search=${encodeURIComponent(keyword)}&limit=50`;
  const res = await throttledFetch(url, {}, rateLimitMs);
  if (!res.ok) {
    throw new Error(`remotive:${keyword} responded ${res.status}`);
  }
  const body = await res.json();
  return (body.jobs || []).map((job) => ({ ...job, __keyword: keyword }));
}
