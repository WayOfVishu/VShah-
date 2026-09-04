/** The only part of the site that talks to the backend.
 *
 * Page content is bundled at build time (see vite.config.js), so the API is
 * used exclusively by the live demos. That means a backend that is down,
 * cold-starting, or simply not deployed yet degrades one panel instead of the
 * whole site — which is also what makes the static-CDN + small-VPS hosting
 * split work.
 */

// Same-origin in production; the Vite dev server proxies /api to :8000.
// VITE_API_BASE overrides it when the API lives on another host.
const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');

const TIMEOUT_MS = 8000;

export class ApiError extends Error {
  constructor(message, { status = 0, cause } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.cause = cause;
  }
}

async function request(path, options = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(`${BASE}${path}`, { ...options, signal: ctrl.signal });

    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body?.detail) {
          detail = Array.isArray(body.detail)
            ? body.detail.map((d) => d.msg || d).join('; ')
            : body.detail;
        }
      } catch {
        /* non-JSON error body; the status line is all we get */
      }
      throw new ApiError(detail, { status: res.status });
    }

    return await res.json();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err.name === 'AbortError') {
      throw new ApiError('the API did not answer in time', { cause: err });
    }
    throw new ApiError('could not reach the API', { cause: err });
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health: () => request('/api/health'),
  remoteSamples: () => request('/api/demos/remote-classifier/samples'),
  classifyRemote: (payload) =>
    request('/api/demos/remote-classifier', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
};
