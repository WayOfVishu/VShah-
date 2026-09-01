// Tier 2 connector: WeWorkRemotely's public per-category RSS feeds (PRD
// req. 2). No auth. WWR doesn't offer keyword search, only category feeds,
// so this pulls a small set of dev/data-relevant categories and lets
// discover.js's dedup + Tier 2 keyword filtering narrow it further.

import { XMLParser } from "fast-xml-parser";

const DEFAULT_CATEGORIES = ["remote-programming-jobs", "remote-data-jobs"];

const parser = new XMLParser({ ignoreAttributes: false });

function stripHtml(html) {
  if (!html) return null;
  return html.replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
}

function parseItem(item, category) {
  // WWR titles are usually "Company: Job Title"
  const [company, ...rest] = String(item.title || "").split(":");
  const title = rest.length > 0 ? rest.join(":").trim() : item.title;

  return {
    title: title || item.title,
    company: rest.length > 0 ? company.trim() : "Unknown",
    location: item.region || null,
    description: stripHtml(item.description),
    apply_url: item.link,
    posted_date: item.pubDate || null,
    category,
  };
}

export async function fetchPostings(categories = DEFAULT_CATEGORIES, { throttledFetch, rateLimitMs }) {
  const results = [];
  for (const category of categories) {
    const url = `https://weworkremotely.com/categories/${category}.rss`;
    const res = await throttledFetch(
      url,
      { headers: { "User-Agent": "Mozilla/5.0 (compatible; job-discovery-bot/1.0)" } },
      rateLimitMs
    );
    if (!res.ok) {
      throw new Error(`weworkremotely:${category} responded ${res.status}`);
    }
    const xml = await res.text();
    const parsed = parser.parse(xml);
    const items = parsed?.rss?.channel?.item;
    const list = Array.isArray(items) ? items : items ? [items] : [];
    results.push(...list.map((item) => parseItem(item, category)));
  }
  return results;
}
