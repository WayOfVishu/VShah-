// PRD req. 5: per-host throttle (config-driven rateLimitMs) with exponential
// backoff on HTTP 429. Tier 2 connectors and the career-page connector share
// this so "free to scrape" never becomes "unthrottled."

const MAX_RETRIES = 4;

function defaultSleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// fetchImpl/sleepImpl are injectable so tests can exercise the backoff curve
// without real network calls or real waiting.
export function createRateLimiter({ fetchImpl = fetch, sleepImpl = defaultSleep } = {}) {
  const lastRequestAtByHost = new Map();

  async function throttledFetch(url, options, rateLimitMs) {
    const host = new URL(url).host;
    const last = lastRequestAtByHost.get(host) || 0;
    const wait = rateLimitMs - (Date.now() - last);
    if (wait > 0) await sleepImpl(wait);

    let attempt = 0;
    while (true) {
      lastRequestAtByHost.set(host, Date.now());
      const res = await fetchImpl(url, options);
      if (res.status !== 429 || attempt >= MAX_RETRIES) return res;
      attempt++;
      await sleepImpl(rateLimitMs * 2 ** attempt);
    }
  }

  return { throttledFetch };
}
