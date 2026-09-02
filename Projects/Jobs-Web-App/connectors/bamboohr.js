// Tier 1 connector: BambooHR's public careers list. No auth.
// https://{slug}.bamboohr.com/careers/list
//
// The list gives titles and locations but no description, and the ingest
// gate's experience cap reads descriptions — so this takes the same shape as
// the Workday connector: a cheap list pass, then a detail request only for
// postings the caller says are still in the running after the title gates.
//
// BambooHR boards are small (Showpass, a Calgary company, has three), so the
// detail pass costs a handful of requests rather than hundreds.

const detailUrl = (slug, id) => `https://${slug}.bamboohr.com/careers/${id}/detail`;

export function applyUrl(slug, id) {
  return `https://${slug}.bamboohr.com/careers/${id}`;
}

export async function probe(slug, { throttledFetch = fetch, rateLimitMs = 1500 } = {}) {
  try {
    const res = await throttledFetch(
      `https://${slug}.bamboohr.com/careers/list`,
      { headers: { accept: "application/json" } },
      rateLimitMs
    );
    if (!res.ok) return false;
    const body = await res.json();
    return Array.isArray(body.result) && body.result.length > 0;
  } catch {
    return false;
  }
}

export async function fetchPostings(
  entry,
  { throttledFetch, rateLimitMs = 1500, shouldFetchDetail = null } = {}
) {
  const slug = entry.slug || entry;
  const res = await throttledFetch(
    `https://${slug}.bamboohr.com/careers/list`,
    { headers: { accept: "application/json" } },
    rateLimitMs
  );
  if (!res.ok) {
    throw new Error(`bamboohr:${slug} responded ${res.status}`);
  }
  const body = await res.json();

  const postings = (body.result || []).map((job) => ({
    ...job,
    __slug: slug,
    __company: entry.name || slug,
    __applyUrl: applyUrl(slug, job.id),
  }));

  if (typeof shouldFetchDetail === "function") {
    for (const posting of postings) {
      if (!shouldFetchDetail(posting)) continue;
      try {
        const d = await throttledFetch(
          detailUrl(slug, posting.id),
          { headers: { accept: "application/json" } },
          rateLimitMs
        );
        if (!d.ok) continue;
        const opening = (await d.json())?.result?.jobOpening;
        if (!opening) continue;
        posting.__description = opening.description || null;
        posting.__datePosted = opening.datePosted || null;
        if (opening.jobOpeningShareUrl) posting.__applyUrl = opening.jobOpeningShareUrl;
      } catch {
        // Keep the list-level record; a failed detail fetch is not a lost posting.
      }
    }
  }

  return postings;
}
