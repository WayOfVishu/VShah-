// Tier 2 connector: RemoteOK's public JSON API (PRD req. 2). No auth.
// RemoteOK's API terms ask for an attributing link-back; apply_url does that.
// The API doesn't support reliable per-keyword search, so this fetches the
// full current listing once per run and filters locally against the
// configured keyword list — one request, not one per keyword.

const BASE = "https://remoteok.com/api";

export async function fetchPostings(keywords, { throttledFetch, rateLimitMs }) {
  const res = await throttledFetch(
    BASE,
    { headers: { "User-Agent": "Mozilla/5.0 (compatible; job-discovery-bot/1.0)" } },
    rateLimitMs
  );
  if (!res.ok) {
    throw new Error(`remoteok responded ${res.status}`);
  }
  const body = await res.json();
  const jobs = (Array.isArray(body) ? body : []).filter((j) => j.id); // first element is a legal notice, not a job

  if (!keywords || keywords.length === 0) return jobs;
  const lowerKeywords = keywords.map((k) => k.toLowerCase());
  return jobs.filter((job) => {
    const haystack = `${job.position || ""} ${(job.tags || []).join(" ")}`.toLowerCase();
    return lowerKeywords.some((k) => haystack.includes(k));
  });
}
