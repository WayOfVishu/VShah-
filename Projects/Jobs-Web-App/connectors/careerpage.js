// Tier 2 connector: company career pages exposing schema.org `JobPosting`
// markup (PRD req. 3). Rendered via Playwright + headless Chrome.
//
// Lightpanda was the PRD's original choice, but it has no Windows build
// path (Linux/macOS/Nix only, requires building V8 from source) and this
// machine has neither a supported OS nor WSL — so this uses the PRD's
// named v1.5 fallback (§7 Technical Considerations) instead. Plain
// page-load-and-read, no interaction scripting, matching the same scope
// Lightpanda would have had.

import { chromium } from "playwright";

function extractJobPostings(jsonLdTexts, pageUrl) {
  const postings = [];
  for (const raw of jsonLdTexts) {
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      continue; // malformed JSON-LD block; skip, don't fail the whole page
    }
    const items = Array.isArray(parsed) ? parsed : [parsed];
    for (const item of items) {
      const candidates = item["@graph"] ? item["@graph"] : [item];
      for (const c of candidates) {
        const types = Array.isArray(c["@type"]) ? c["@type"] : [c["@type"]];
        if (types.includes("JobPosting")) {
          postings.push({ ...c, __pageUrl: pageUrl });
        }
      }
    }
  }
  return postings;
}

// Throws if no JobPosting markup is found — discover.js treats that as a
// render/fetch failure (req. 4), not "no new postings."
export async function fetchPostings(url, { timeoutMs = 20000 } = {}) {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    const jsonLdTexts = await page.$$eval('script[type="application/ld+json"]', (nodes) =>
      nodes.map((n) => n.textContent)
    );
    const postings = extractJobPostings(jsonLdTexts, url);
    if (postings.length === 0) {
      throw new Error(`no schema.org JobPosting markup found at ${url}`);
    }
    return postings;
  } finally {
    await browser.close();
  }
}
