import test from "node:test";
import assert from "node:assert/strict";
import { buildDedupIndex, findDuplicate } from "./dedup.js";

const existing = [
  { id: 1, title: "Senior Backend Engineer", company: "Acme Corp", location: "Remote", apply_url: "https://boards.greenhouse.io/acme/jobs/1" },
  { id: 2, title: "Data Scientist", company: "Widgets Inc", location: "Toronto, ON", apply_url: "https://jobs.lever.co/widgets/2" },
];

test("collapses a true cross-posted duplicate (same role, different board)", () => {
  const index = buildDedupIndex(existing);
  const candidate = {
    title: "Senior Backend Engineer",
    company: "Acme Corp",
    location: "Remote",
    apply_url: "https://jobs.ashbyhq.com/acme/1", // different URL, same role
  };
  const match = findDuplicate(candidate, index);
  assert.equal(match?.id, 1);
});

test("does not collapse a similar-but-distinct near-miss", () => {
  const index = buildDedupIndex(existing);
  const candidate = {
    title: "Senior Frontend Engineer", // different discipline, same company/location
    company: "Acme Corp",
    location: "Remote",
    apply_url: "https://boards.greenhouse.io/acme/jobs/99",
  };
  const match = findDuplicate(candidate, index);
  assert.equal(match, null);
});

test("matches on identical apply_url even if fuzzy text drifts", () => {
  const index = buildDedupIndex(existing);
  const candidate = {
    title: "Sr. Backend Engineer (Remote, US)", // reworded title
    company: "Acme Corp",
    location: "Remote",
    apply_url: "https://boards.greenhouse.io/acme/jobs/1", // exact same URL
  };
  const match = findDuplicate(candidate, index);
  assert.equal(match?.id, 1);
});
