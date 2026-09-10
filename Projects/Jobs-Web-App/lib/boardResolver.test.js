import test from "node:test";
import assert from "node:assert/strict";
import Database from "better-sqlite3";
import { applyMigrations } from "../db/migrate.js";
import { slugCandidates, resolveBoards, cachedBoards } from "./boardResolver.js";

function freshDb() {
  const db = new Database(":memory:");
  applyMigrations(db);
  return db;
}

// Only the platforms that exist in PROBERS can be auto-resolved, so these
// fixtures use greenhouse/ashby. Nothing here reaches the network: every test
// either supplies an override or relies on the cache being pre-seeded.
const platforms = {
  greenhouse: { enabled: true, autoResolve: true, rateLimitMs: 2000 },
  ashby: { enabled: true, autoResolve: true, rateLimitMs: 2000 },
  workday: { enabled: true, autoResolve: false, rateLimitMs: 600 },
};

function seedCache(db, company, platform, identifier, origin = "probe") {
  db.prepare(
    `INSERT INTO board_cache (company, platform, identifier, found, origin, checked_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`
  ).run(company, platform, identifier === null ? null : JSON.stringify(identifier), identifier ? 1 : 0, origin);
}

test("slug candidates cover the two spellings boards actually use", () => {
  assert.deepEqual(slugCandidates("Neo Financial"), ["neofinancial", "neo-financial"]);
  assert.deepEqual(slugCandidates("1Password"), ["1password"]);
  assert.deepEqual(slugCandidates("Top Hat"), ["tophat", "top-hat"]);
});

test("an override is used verbatim and never probed", async () => {
  const db = freshDb();
  const config = {
    platforms,
    companies: {
      Enbridge: { boards: { workday: { tenant: "enbridge", host: "wd3", site: "ENBRIDGE_Careers" } } },
    },
    resolution: { cacheDays: 30 },
  };
  // autoResolve is false for workday and the other platforms are not listed
  // for this company, so nothing here can reach the network.
  config.companies.Enbridge.platforms = [];

  const { entries, report } = await resolveBoards(config, db);
  assert.equal(entries.length, 1);
  assert.deepEqual(entries[0], {
    name: "Enbridge",
    platform: "workday",
    rateLimitMs: 600,
    tenant: "enbridge",
    host: "wd3",
    site: "ENBRIDGE_Careers",
  });
  assert.equal(report.overrides, 1);
  assert.equal(report.probed, 0);
});

test("a cached hit is reused instead of re-probed", async () => {
  const db = freshDb();
  seedCache(db, "StackAdapt", "greenhouse", "stackadapt");
  const config = {
    platforms: { greenhouse: platforms.greenhouse },
    companies: { StackAdapt: {} },
    resolution: { cacheDays: 30 },
  };

  const { entries, report } = await resolveBoards(config, db);
  assert.equal(report.probed, 0, "a fresh cache entry must not trigger a probe");
  assert.equal(report.cached, 1);
  assert.deepEqual(entries, [{ name: "StackAdapt", platform: "greenhouse", rateLimitMs: 2000, slug: "stackadapt" }]);
});

test("a cached miss is reused too, which is what keeps the cross-product affordable", async () => {
  const db = freshDb();
  // Most cells in companies x platforms are misses. Re-probing them every run
  // would be the bulk of the work, so a negative answer is cached as well.
  seedCache(db, "StackAdapt", "ashby", null);
  const config = {
    platforms: { ashby: platforms.ashby },
    companies: { StackAdapt: {} },
    resolution: { cacheDays: 30 },
  };

  const { entries, report } = await resolveBoards(config, db);
  assert.equal(report.probed, 0);
  assert.equal(report.cached, 1);
  assert.equal(entries.length, 0);
});

test("a disabled platform is not searched even when a company overrides it", async () => {
  const db = freshDb();
  const config = {
    platforms: { greenhouse: { enabled: false, autoResolve: true } },
    companies: { Acme: { boards: { greenhouse: "acme" } } },
    resolution: { cacheDays: 30 },
  };

  const { entries } = await resolveBoards(config, db);
  assert.equal(entries.length, 0);
});

test("`platforms` on a company narrows which boards are searched", async () => {
  const db = freshDb();
  seedCache(db, "Acme", "greenhouse", "acme");
  seedCache(db, "Acme", "ashby", "acme");
  const config = {
    platforms,
    // Pinning to greenhouse is how a slug that collides with an unrelated
    // company's board on another platform is kept out of the feed.
    companies: { Acme: { platforms: ["greenhouse"] } },
    resolution: { cacheDays: 30 },
  };

  const { entries } = await resolveBoards(config, db);
  assert.deepEqual(entries.map((e) => e.platform), ["greenhouse"]);
});

test("a company resolving on two platforms yields both boards", async () => {
  const db = freshDb();
  // Dual-posting is the case the old company-to-platform pairing could not
  // express at all. Duplicate postings are collapsed later by lib/dedup.js.
  seedCache(db, "Waabi", "greenhouse", "waabi");
  seedCache(db, "Waabi", "ashby", "waabi");
  const config = {
    platforms,
    companies: { Waabi: {} },
    resolution: { cacheDays: 30 },
  };

  const { entries } = await resolveBoards(config, db);
  assert.deepEqual(entries.map((e) => e.platform).sort(), ["ashby", "greenhouse"]);
});

test("an expired cache entry is re-probed, a fresh one is not", async () => {
  const db = freshDb();
  seedCache(db, "Acme", "greenhouse", "acme");
  db.prepare("UPDATE board_cache SET checked_at = datetime('now', '-90 days') WHERE company = 'Acme'").run();

  const config = {
    platforms: { greenhouse: platforms.greenhouse },
    companies: { Acme: {} },
    resolution: { cacheDays: 1 },
  };

  const probers = { greenhouse: { probe: async (slug) => slug === "acme" } };
  const { report, entries } = await resolveBoards(config, db, { probers });
  assert.equal(report.cached, 0, "a 90-day-old entry under a 1-day TTL must not count as cached");
  assert.equal(report.probed, 1);
  assert.equal(entries.length, 1);
});

test("a probe that throws is not cached as a miss", async () => {
  const db = freshDb();
  const config = {
    platforms: { greenhouse: platforms.greenhouse },
    companies: { Acme: {} },
    resolution: { cacheDays: 30 },
  };

  // A timeout or a 503 says nothing about whether the board exists. Recording
  // it as absent would hide the company until the entry expired, so an errored
  // probe leaves the cache alone and the next run asks again.
  const probers = { greenhouse: { probe: async () => { throw new Error("ETIMEDOUT"); } } };
  const { report } = await resolveBoards(config, db, { probers });

  assert.equal(report.errors, 1);
  assert.equal(cachedBoards(db).length, 0, "an errored probe must not leave a cached verdict");
});

test("an override never expires, however old the row is", async () => {
  const db = freshDb();
  const config = {
    platforms: { workday: platforms.workday },
    companies: { BMO: { boards: { workday: { tenant: "bmo", host: "wd3", site: "External" } } } },
    resolution: { cacheDays: 1 },
  };

  await resolveBoards(config, db);
  db.prepare("UPDATE board_cache SET checked_at = datetime('now', '-999 days')").run();

  const { entries } = await resolveBoards(config, db);
  assert.equal(entries.length, 1, "a hand-stated board is not a guess and does not go stale");
  assert.equal(cachedBoards(db)[0].origin, "override");
});
