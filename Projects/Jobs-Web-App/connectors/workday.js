// Tier 1 connector: Workday's public CXS job-board API. No auth, no bot
// defense — it is the same JSON the myworkdayjobs.com careers page fetches to
// render itself.
//
// This is where Calgary's large employers actually post. Greenhouse, Lever and
// Ashby cover startups and scale-ups; the energy majors, the banks, and the
// utilities that do most of the hiring in Alberta are almost all on Workday.
//
// A board is addressed by three parts, not a single slug:
//   tenant  the subdomain and the path segment   (suncor)
//   host    which Workday cell it lives in       (wd1, wd3, wd5, wd10, wd12)
//   site    the career site name within it       (Suncor_External)
// so `config/sources.json` carries an object per board rather than a string.
// `scripts/probe-workday.js` finds the three parts for a company you name.
//
// Two things make this connector different from the slug-based ones:
//
// 1. It searches rather than pulling the whole board. BMO's board is 927
//    postings; `searchText: "software engineer"` returns 54 of them, server
//    side. Pulling all 927 to throw away 873 would be rude to a host that
//    isn't charging us and slow for no gain.
//
// 2. The list endpoint gives no description, and the ingest gate needs one to
//    apply the experience cap. Descriptions come from a second request per
//    posting, so the caller passes `shouldFetchDetail` to say which postings
//    are worth it — in practice, the ones whose *title* already passed the
//    role and seniority gates. That turns "one request per posting" into "one
//    request per posting we might actually keep."

const PAGE_SIZE = 20; // Workday caps a page at 20 regardless of what you ask for.
const DEFAULT_MAX_PER_QUERY = 100;

function boardUrl({ tenant, host, site }) {
  return `https://${tenant}.${host}.myworkdayjobs.com/wday/cxs/${tenant}/${site}`;
}

// The public, human-facing URL for a posting — what belongs in apply_url.
// The CXS path is an API detail and 404s in a browser.
export function applyUrl(board, externalPath) {
  return `https://${board.tenant}.${board.host}.myworkdayjobs.com/en-US/${board.site}${externalPath}`;
}

// Workday's list endpoint dates a posting only in words: "Posted Today",
// "Posted Yesterday", "Posted 3 Days Ago", "Posted 30+ Days Ago". The ingest
// gate needs a real date to apply maxAgeDays, so parse them back to one.
//
// Returns null for anything unrecognized rather than guessing a date. An
// undated posting is treated as fresh on first sight (see isFresh), which is
// the right call: "we couldn't read the date" is not "it's old".
export function parsePostedOn(text, now = new Date()) {
  if (!text) return null;
  const s = String(text).toLowerCase();
  if (/just posted|posted today/.test(s)) return new Date(now).toISOString();
  if (/posted yesterday/.test(s)) {
    const d = new Date(now);
    d.setDate(d.getDate() - 1);
    return d.toISOString();
  }
  const m = s.match(/posted\s+(\d+)\+?\s+(day|week|month)s?\s+ago/);
  if (!m) return null;
  const n = Number(m[1]);
  const d = new Date(now);
  if (m[2] === "day") d.setDate(d.getDate() - n);
  else if (m[2] === "week") d.setDate(d.getDate() - n * 7);
  else d.setMonth(d.getMonth() - n);
  return d.toISOString();
}

async function fetchPage(board, searchText, offset, { throttledFetch, rateLimitMs }) {
  const res = await throttledFetch(
    `${boardUrl(board)}/jobs`,
    {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ appliedFacets: {}, limit: PAGE_SIZE, offset, searchText }),
    },
    rateLimitMs
  );
  if (!res.ok) {
    throw new Error(`workday:${board.tenant}/${board.site} responded ${res.status}`);
  }
  return res.json();
}

// One posting's full record. Gives the description the experience cap needs,
// the exact location (the list says "3 Locations" when a posting spans
// several), and a real ISO startDate instead of "Posted 2 Days Ago".
async function fetchDetail(board, externalPath, { throttledFetch, rateLimitMs }) {
  const res = await throttledFetch(
    `${boardUrl(board)}${externalPath}`,
    { headers: { accept: "application/json" } },
    rateLimitMs
  );
  if (!res.ok) return null; // A posting pulled between list and detail is not a board failure.
  const body = await res.json();
  return body.jobPostingInfo || null;
}

export async function probe(board, { throttledFetch, rateLimitMs = 1500 } = {}) {
  try {
    const body = await fetchPage(board, "", 0, { throttledFetch, rateLimitMs });
    return typeof body.total === "number" && body.total > 0;
  } catch {
    return false;
  }
}

// Searches one Workday board once per keyword and returns the union, deduped
// by externalPath — a "software engineer" and a "data engineer" query overlap.
//
// Throws only if every keyword query failed, so one bad search term does not
// mark a working board as a failed source.
export async function fetchPostings(
  entry,
  { throttledFetch, rateLimitMs = 1500, keywords = [""], shouldFetchDetail = null, maxPerQuery = DEFAULT_MAX_PER_QUERY } = {}
) {
  const board = { tenant: entry.tenant, host: entry.host, site: entry.site };
  const byPath = new Map();
  const errors = [];

  for (const keyword of keywords.length ? keywords : [""]) {
    try {
      let offset = 0;
      let total = Infinity;
      while (offset < Math.min(total, maxPerQuery)) {
        const body = await fetchPage(board, keyword, offset, { throttledFetch, rateLimitMs });
        total = typeof body.total === "number" ? body.total : 0;
        const page = body.jobPostings || [];
        if (page.length === 0) break;
        for (const job of page) {
          if (!byPath.has(job.externalPath)) byPath.set(job.externalPath, job);
        }
        offset += PAGE_SIZE;
      }
    } catch (err) {
      errors.push(err);
    }
  }

  if (byPath.size === 0 && errors.length > 0) throw errors[0];

  const postings = [...byPath.values()].map((job) => ({
    ...job,
    __board: board,
    __company: entry.name,
    __applyUrl: applyUrl(board, job.externalPath),
    __postedDate: parsePostedOn(job.postedOn),
  }));

  // Second pass: descriptions, but only for the postings the caller says are
  // still in the running after the title-level gates.
  if (typeof shouldFetchDetail === "function") {
    for (const posting of postings) {
      if (!shouldFetchDetail(posting)) continue;
      try {
        const info = await fetchDetail(board, posting.externalPath, { throttledFetch, rateLimitMs });
        if (!info) continue;
        posting.__description = info.jobDescription || null;
        posting.__location = info.location || posting.locationsText;
        posting.__startDate = info.startDate || null;
        posting.__timeType = info.timeType || null;
        if (info.externalUrl) posting.__applyUrl = info.externalUrl;
      } catch {
        // A detail fetch that fails leaves the list-level record intact rather
        // than dropping a posting we already know exists.
      }
    }
  }

  return postings;
}
