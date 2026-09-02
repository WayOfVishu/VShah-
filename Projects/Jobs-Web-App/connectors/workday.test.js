import test from "node:test";
import assert from "node:assert/strict";
import { parsePostedOn, applyUrl, fetchPostings } from "./workday.js";
import { normalize } from "../lib/normalize.js";

const NOW = new Date("2026-09-02T12:00:00Z");

test("parses Workday's relative posting dates back into real ones", () => {
  assert.equal(parsePostedOn("Posted Today", NOW).slice(0, 10), "2026-09-02");
  assert.equal(parsePostedOn("Posted Yesterday", NOW).slice(0, 10), "2026-09-01");
  assert.equal(parsePostedOn("Posted 3 Days Ago", NOW).slice(0, 10), "2026-08-30");
  assert.equal(parsePostedOn("Posted 2 Weeks Ago", NOW).slice(0, 10), "2026-08-19");
  // "30+" is Workday's ceiling, not a real age. Treating it as exactly 30 days
  // is the conservative read: it can only make a posting look fresher than it
  // is by the amount maxAgeDays would reject anyway.
  assert.equal(parsePostedOn("Posted 30+ Days Ago", NOW).slice(0, 10), "2026-08-03");
});

test("returns null for an unreadable date rather than guessing one", () => {
  // isFresh() treats a null posted_date as fresh-on-first-sight, which is the
  // right failure mode: a parse we don't recognize must not silently become
  // "posted today" and defeat the freshness gate.
  assert.equal(parsePostedOn("Recently posted", NOW), null);
  assert.equal(parsePostedOn(""), null);
  assert.equal(parsePostedOn(undefined), null);
});

test("builds the human apply URL, not the CXS API path", () => {
  const url = applyUrl({ tenant: "suncor", host: "wd1", site: "Suncor_External" }, "/job/Calgary/Dev_R1");
  assert.equal(url, "https://suncor.wd1.myworkdayjobs.com/en-US/Suncor_External/job/Calgary/Dev_R1");
  assert.ok(!url.includes("/wday/cxs/"));
});

// --- normalizer -----------------------------------------------------------

test("normalizes a Workday posting into the unified schema", () => {
  const raw = {
    title: "Full Stack Engineer (AI-Enabled)",
    externalPath: "/job/Calgary-AB-CAN/Full-Stack-Engineer_R123",
    locationsText: "Calgary, AB, CAN",
    postedOn: "Posted 2 Days Ago",
    bulletFields: ["R123"],
    __company: "BMO",
    __applyUrl: "https://bmo.wd3.myworkdayjobs.com/en-US/External/job/Calgary-AB-CAN/Full-Stack-Engineer_R123",
    __postedDate: parsePostedOn("Posted 2 Days Ago", NOW),
    __description: "<p>Build things. 1 year of experience.</p>",
  };
  const job = normalize("workday", raw, "BMO");

  assert.equal(job.source, "workday");
  assert.equal(job.job_id, "R123"); // requisition id, not the URL path
  assert.equal(job.company, "BMO");
  assert.equal(job.location, "Calgary, AB, CAN");
  assert.equal(job.description, "Build things. 1 year of experience.");
  assert.equal(job.posted_date.slice(0, 10), "2026-08-31");
  assert.equal(job.remote_status, null);
});

test("reads remote out of a bilingual Workday location string", () => {
  const job = normalize("workday", {
    title: "Platform Engineer",
    bulletFields: ["R9"],
    locationsText: "REMOTE/TELETRAVAIL, ON, CAN",
    __company: "BMO",
  });
  assert.equal(job.remote_status, "remote");
});

test('drops the "3 Locations" placeholder rather than storing it as a location', () => {
  // The list endpoint writes a count where a multi-city posting's locations
  // go. Storing that verbatim would bucket the posting as an unparseable
  // location instead of leaving it unknown.
  const job = normalize("workday", {
    title: "Data Engineer",
    bulletFields: ["R7"],
    locationsText: "3 Locations",
    __company: "Suncor",
  });
  assert.equal(job.location, null);
});

test("prefers the detail pass's exact location and ISO date over the list's", () => {
  const job = normalize("workday", {
    title: "Data Engineer",
    bulletFields: ["R7"],
    locationsText: "3 Locations",
    __location: "Calgary, AB, CAN",
    __postedDate: "2026-08-01T00:00:00.000Z",
    __startDate: "2026-08-28",
    __company: "Suncor",
  });
  assert.equal(job.location, "Calgary, AB, CAN");
  assert.equal(job.posted_date, "2026-08-28");
});

// --- fetch behaviour (no network) -----------------------------------------

function fakeFetch(pages) {
  return async (url, options) => {
    if (options?.method === "POST") {
      const { offset, searchText } = JSON.parse(options.body);
      const all = pages[searchText] || [];
      return {
        ok: true,
        json: async () => ({ total: all.length, jobPostings: all.slice(offset, offset + 20) }),
      };
    }
    return { ok: true, json: async () => ({ jobPostingInfo: { jobDescription: "detail body", location: "Calgary, AB" } }) };
  };
}

const board = { name: "Test", tenant: "t", host: "wd3", site: "External" };

test("unions results across search keywords and dedups the overlap", async () => {
  const a = { title: "Software Engineer", externalPath: "/job/1", bulletFields: ["R1"], postedOn: "Posted Today" };
  const b = { title: "Data Engineer", externalPath: "/job/2", bulletFields: ["R2"], postedOn: "Posted Today" };
  const postings = await fetchPostings(board, {
    throttledFetch: fakeFetch({ "software engineer": [a, b], "data engineer": [b] }),
    keywords: ["software engineer", "data engineer"],
  });
  assert.equal(postings.length, 2);
});

test("only spends a detail request on postings the caller still wants", async () => {
  let details = 0;
  const raw = [
    { title: "Software Engineer", externalPath: "/job/1", bulletFields: ["R1"], postedOn: "Posted Today" },
    { title: "Senior Software Engineer", externalPath: "/job/2", bulletFields: ["R2"], postedOn: "Posted Today" },
    { title: "Welder", externalPath: "/job/3", bulletFields: ["R3"], postedOn: "Posted Today" },
  ];
  const counting = async (url, options) => {
    if (options?.method !== "POST") details++;
    return fakeFetch({ "": raw })(url, options);
  };
  const postings = await fetchPostings(board, {
    throttledFetch: counting,
    keywords: [""],
    shouldFetchDetail: (j) => j.title === "Software Engineer",
  });

  assert.equal(details, 1, "should not fetch details for the senior or the welder");
  assert.equal(postings.find((p) => p.title === "Software Engineer").__description, "detail body");
  assert.equal(postings.find((p) => p.title === "Welder").__description, undefined);
});

test("one failing keyword does not fail a board that answered others", async () => {
  const flaky = async (url, options) => {
    const { searchText } = JSON.parse(options.body);
    if (searchText === "bad") return { ok: false, status: 500 };
    return { ok: true, json: async () => ({ total: 1, jobPostings: [{ title: "Dev", externalPath: "/j", bulletFields: ["R"], postedOn: "Posted Today" }] }) };
  };
  const postings = await fetchPostings(board, { throttledFetch: flaky, keywords: ["bad", "good"] });
  assert.equal(postings.length, 1);
});

test("throws when every keyword failed, so the source is marked unhealthy", async () => {
  const dead = async () => ({ ok: false, status: 503 });
  await assert.rejects(() => fetchPostings(board, { throttledFetch: dead, keywords: ["a", "b"] }), /responded 503/);
});
