// Tier 1 connector: Lever's public JSON postings API. No auth, no ToS
// issue (PRD req. 1). https://github.com/lever/postings-api

const BASE = "https://api.lever.co/v0/postings";

export async function probe(slug) {
  const res = await fetch(`${BASE}/${slug}?mode=json&limit=1`);
  if (!res.ok) return false;
  const body = await res.json();
  return Array.isArray(body) && body.length > 0;
}

export async function fetchPostings(slug) {
  const res = await fetch(`${BASE}/${slug}?mode=json`);
  if (!res.ok) {
    throw new Error(`lever:${slug} responded ${res.status}`);
  }
  const body = await res.json();
  return (Array.isArray(body) ? body : []).map((job) => ({ ...job, __slug: slug }));
}
