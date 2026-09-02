// Tier 1 connector: Recruitee's public offers API. No auth.
// https://{slug}.recruitee.com/api/offers/
//
// One request returns every open posting with its description inline, so like
// Workable there is no detail pass.
//
// Recruitee reports remote status as real booleans (`remote`, `hybrid`,
// `on_site`) rather than leaving it to be inferred from a location string.
// That is worth more than it sounds: a Calgary-anchored search lives or dies
// on correctly identifying remote roles, and every other connector here makes
// us guess by regexing the word "remote" out of free text.

export async function probe(slug, { throttledFetch = fetch, rateLimitMs = 1500 } = {}) {
  try {
    const res = await throttledFetch(
      `https://${slug}.recruitee.com/api/offers/`,
      { headers: { accept: "application/json" } },
      rateLimitMs
    );
    if (!res.ok) return false;
    const body = await res.json();
    return Array.isArray(body.offers) && body.offers.length > 0;
  } catch {
    return false;
  }
}

export async function fetchPostings(entry, { throttledFetch, rateLimitMs = 1500 } = {}) {
  const slug = entry.slug || entry;
  const res = await throttledFetch(
    `https://${slug}.recruitee.com/api/offers/`,
    { headers: { accept: "application/json" } },
    rateLimitMs
  );
  if (!res.ok) {
    throw new Error(`recruitee:${slug} responded ${res.status}`);
  }
  const body = await res.json();
  const company = entry.name || body.offers?.[0]?.company_name || slug;
  return (body.offers || []).map((job) => ({ ...job, __company: company }));
}
