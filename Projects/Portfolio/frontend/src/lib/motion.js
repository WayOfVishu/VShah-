/** Scroll-driven behaviour: reveals, counters, the nav, the clock, and the
 *  cursor glow on cards.
 *
 *  All of it is IntersectionObserver and rAF. No scroll listeners doing layout
 *  reads, because that is how a page like this ends up janky. */

const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---------------------------------------------------------------- reveals */

export function initReveals(root = document) {
  const targets = [...root.querySelectorAll('[data-reveal]')];
  if (!targets.length) return;

  if (REDUCED || !('IntersectionObserver' in window)) {
    targets.forEach((el) => el.classList.add('is-revealed'));
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add('is-revealed');
        io.unobserve(entry.target); // reveal once, then stop watching
      }
    },
    { rootMargin: '0px 0px -12% 0px', threshold: 0.06 }
  );

  targets.forEach((el) => io.observe(el));
}

/* --------------------------------------------------------------- counters */

/** Ease-out so the number decelerates into its final value instead of
 *  stopping dead. */
const easeOut = (t) => 1 - Math.pow(1 - t, 3);

function formatCount(n, format) {
  switch (format) {
    case 'compact':
      return n >= 1_000_000
        ? `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M+`
        : n >= 1000
          ? `${Math.round(n / 1000)}K+`
          : String(Math.round(n));
    case 'percent':
      return `${Math.round(n)}%`;
    case 'plus':
      return `${Math.round(n)}+`;
    default:
      return String(Math.round(n));
  }
}

/** Count an element up when it scrolls into view. Elements carry
 *  data-count-to / data-count-format / data-count-display. */
export function initCounters(root = document) {
  const targets = [...root.querySelectorAll('[data-count-to]')];
  if (!targets.length) return;

  const settle = (el) => {
    el.textContent = el.dataset.countDisplay || formatCount(Number(el.dataset.countTo), el.dataset.countFormat);
  };

  if (REDUCED || !('IntersectionObserver' in window)) {
    targets.forEach(settle);
    return;
  }

  const run = (el) => {
    const to = Number(el.dataset.countTo) || 0;
    const format = el.dataset.countFormat;
    // "6-fig" and friends have no numeric ramp worth watching.
    if (format === 'literal') return settle(el);

    const dur = 1500;
    const t0 = performance.now();

    const step = (now) => {
      const p = Math.min((now - t0) / dur, 1);
      el.textContent = formatCount(to * easeOut(p), format);
      if (p < 1) requestAnimationFrame(step);
      else settle(el); // land on the exact display string, not a rounding of it
    };
    requestAnimationFrame(step);
  };

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        run(entry.target);
        io.unobserve(entry.target);
      }
    },
    { threshold: 0.4 }
  );

  targets.forEach((el) => {
    el.textContent = formatCount(0, el.dataset.countFormat);
    io.observe(el);
  });
}

/* -------------------------------------------------------------------- nav */

/** Adds .is-stuck once scrolled, and highlights the section in view. */
export function initNav() {
  const nav = document.querySelector('.nav');
  const links = [...document.querySelectorAll('.nav-links a')];
  const sentinel = document.createElement('div');

  if (nav) {
    sentinel.style.cssText = 'position:absolute;top:0;left:0;width:1px;height:60px;pointer-events:none;';
    document.body.prepend(sentinel);
    new IntersectionObserver(
      ([e]) => nav.classList.toggle('is-stuck', !e.isIntersecting),
      { threshold: 0 }
    ).observe(sentinel);
  }

  if (!links.length) return;

  const byId = new Map(
    links.map((a) => [a.getAttribute('href').replace('#', ''), a])
  );
  const sections = [...byId.keys()]
    .map((id) => document.getElementById(id))
    .filter(Boolean);

  if (!sections.length) return;

  // Track which sections are on screen and light the topmost one, so a short
  // section near the bottom of the page still gets its turn.
  const onScreen = new Set();
  const spy = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) onScreen.add(e.target.id);
        else onScreen.delete(e.target.id);
      }
      const current = sections.find((s) => onScreen.has(s.id));
      links.forEach((a) => a.classList.remove('is-current'));
      if (current) byId.get(current.id)?.classList.add('is-current');
    },
    { rootMargin: '-45% 0px -45% 0px', threshold: 0 }
  );

  sections.forEach((s) => spy.observe(s));
}

/* ------------------------------------------------------------------ clock */

/** Live local time where he actually is, which is the small detail that sells
 *  the mission-control conceit. */
export function initClock(el, timeZone = 'America/Edmonton') {
  if (!el) return;

  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  let zoneLabel = 'MT';
  try {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone, timeZoneName: 'short' }).formatToParts(new Date());
    zoneLabel = parts.find((p) => p.type === 'timeZoneName')?.value || zoneLabel;
  } catch {
    /* Intl without zone names; the default label is fine */
  }

  const tick = () => {
    el.innerHTML = `<b>${fmt.format(new Date())}</b> ${zoneLabel}`;
  };
  tick();
  setInterval(tick, 1000);
}

/* ------------------------------------------------------- card cursor glow */

/** Feeds --mx/--my to a card so its radial highlight follows the pointer.
 *  Coalesced into rAF so a fast mouse cannot outrun the compositor. */
export function initCardGlow(root = document) {
  if (REDUCED) return;
  const cards = [...root.querySelectorAll('.card')];
  if (!cards.length || !window.matchMedia('(hover: hover)').matches) return;

  let queued = false;
  let pending = null;

  const flush = () => {
    queued = false;
    if (!pending) return;
    const { card, x, y } = pending;
    card.style.setProperty('--mx', `${x}px`);
    card.style.setProperty('--my', `${y}px`);
    pending = null;
  };

  cards.forEach((card) => {
    card.addEventListener(
      'pointermove',
      (e) => {
        const r = card.getBoundingClientRect();
        pending = { card, x: e.clientX - r.left, y: e.clientY - r.top };
        if (!queued) {
          queued = true;
          requestAnimationFrame(flush);
        }
      },
      { passive: true }
    );
  });
}
