import test from "node:test";
import assert from "node:assert/strict";
import { createRateLimiter } from "./rateLimiter.js";

function fakeResponse(status) {
  return { status };
}

test("throttles consecutive calls to the same host by rateLimitMs", async () => {
  const sleeps = [];
  let now = 0;
  const rl = createRateLimiter({
    fetchImpl: async () => fakeResponse(200),
    sleepImpl: async (ms) => {
      sleeps.push(ms);
      now += ms;
    },
  });

  await rl.throttledFetch("https://example.com/a", {}, 2000);
  // second call happens "instantly" in test time, so it should wait ~2000ms
  await rl.throttledFetch("https://example.com/b", {}, 2000);

  assert.ok(sleeps.some((ms) => ms > 1900 && ms <= 2000), `expected a ~2000ms throttle wait, got ${sleeps}`);
});

test("backs off exponentially on repeated 429s, then succeeds", async () => {
  const statuses = [429, 429, 200];
  const sleeps = [];
  const rl = createRateLimiter({
    fetchImpl: async () => fakeResponse(statuses.shift()),
    sleepImpl: async (ms) => sleeps.push(ms),
  });

  const res = await rl.throttledFetch("https://example.com/c", {}, 1000);

  assert.equal(res.status, 200);
  // first sleep is the pre-request throttle (host unseen -> 0/negative, skipped),
  // then backoff sleeps of rateLimitMs*2^1 and rateLimitMs*2^2
  assert.deepEqual(sleeps, [2000, 4000]);
});

test("gives up after MAX_RETRIES consecutive 429s and returns the 429", async () => {
  const rl = createRateLimiter({
    fetchImpl: async () => fakeResponse(429),
    sleepImpl: async () => {},
  });

  const res = await rl.throttledFetch("https://example.com/d", {}, 100);
  assert.equal(res.status, 429);
});
