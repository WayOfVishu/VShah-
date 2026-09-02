#!/usr/bin/env node
// Finds the three parts of a Workday board so you can add it to
// config/sources.json:  node scripts/probe-workday.js suncor westjet atco
//
// A Workday board is addressed by tenant + host cell + career-site name, and
// only the tenant is guessable from the company name. The other two are not
// published anywhere — the site slug in particular is whatever the employer
// typed when they set the board up ("External", "Careers", "Suncor_External",
// "ENBRIDGE_Careers"). So this brute-forces the small space of both against
// the one thing we do know.
//
// Prints a ready-to-paste sources.json entry for every board that answers.

import { createRateLimiter } from "../lib/rateLimiter.js";

const HOSTS = ["wd1", "wd3", "wd5", "wd10", "wd12", "wd2", "wd101", "wd103"];
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// Ordered cheapest-guess-first: the two generic slugs cover most boards.
const sitesFor = (t) => [
  "External",
  "Careers",
  "careers",
  "external",
  "Search",
  "Jobs",
  `${cap(t)}_External`,
  `${cap(t)}_Careers`,
  `${t}_Careers`,
  `${t}_careers`,
  `${t.toUpperCase()}_Careers`,
  `${cap(t)}Careers`,
  `${t}careers`,
  "External_Careers",
  "ExternalCareerSite",
  "CareerSite",
  "careers-home",
];

const { throttledFetch } = createRateLimiter();
const RATE_MS = 250; // Same host across many guesses; stay polite.

async function tryBoard(tenant, host, site) {
  const url = `https://${tenant}.${host}.myworkdayjobs.com/wday/cxs/${tenant}/${site}/jobs`;
  try {
    const res = await throttledFetch(
      url,
      {
        method: "POST",
        headers: { "content-type": "application/json", accept: "application/json" },
        body: JSON.stringify({ appliedFacets: {}, limit: 1, offset: 0, searchText: "" }),
      },
      RATE_MS
    );
    if (!res.ok) return null;
    const body = await res.json();
    if (typeof body.total !== "number" || body.total === 0) return null;
    return { tenant, host, site, total: body.total };
  } catch {
    return null;
  }
}

async function probeTenant(tenant) {
  const tasks = [];
  for (const host of HOSTS) for (const site of sitesFor(tenant)) tasks.push([host, site]);

  let i = 0;
  let hit = null;
  const worker = async () => {
    while (i < tasks.length && !hit) {
      const [host, site] = tasks[i++];
      const found = await tryBoard(tenant, host, site);
      // First answer wins: a tenant has one board, and the generic slugs are
      // tried first, so this stops as soon as it works rather than
      // enumerating every alias of the same board.
      if (found && !hit) hit = found;
    }
  };
  await Promise.all(Array.from({ length: 12 }, worker));
  return hit;
}

const tenants = process.argv.slice(2);
if (tenants.length === 0) {
  console.error("usage: node scripts/probe-workday.js <tenant> [tenant...]");
  console.error("  tenant is usually the company name lowercased and unspaced: suncor, tcenergy, atb");
  process.exit(1);
}

console.log(`Probing ${tenants.length} tenant(s) across ${HOSTS.length} Workday cells...\n`);

const entries = [];
for (const tenant of tenants) {
  const hit = await probeTenant(tenant);
  if (!hit) {
    console.log(`  ${tenant.padEnd(20)} no public Workday board found`);
    continue;
  }
  console.log(`  ${tenant.padEnd(20)} ${hit.host}/${hit.site} — ${hit.total} postings`);
  entries.push({
    name: cap(tenant),
    platform: "workday",
    tenant: hit.tenant,
    host: hit.host,
    site: hit.site,
    rateLimitMs: 2000,
  });
}

if (entries.length > 0) {
  console.log(`\nPaste into tier1Watchlist in config/sources.json:\n`);
  console.log(entries.map((e) => JSON.stringify(e, null, 2)).join(",\n"));
}
