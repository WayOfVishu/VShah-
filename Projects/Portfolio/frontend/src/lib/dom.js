/** Small DOM helpers. No framework — the page is rendered once from static
 *  data, so a diffing library would be solving a problem this site does not
 *  have. */

/** Escape anything that came from a user before it goes near innerHTML.
 *  Site copy is mine and trusted; demo input is not. */
export const esc = (s) =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Set innerHTML from an array of html strings. */
export const fill = (el, parts) => {
  if (el) el.innerHTML = Array.isArray(parts) ? parts.join('') : parts;
  return el;
};

/** Stagger helper: returns an inline style that offsets a reveal. */
export const delay = (i, step = 70) => `--reveal-delay:${i * step}ms`;

/** "2026-05" -> "May 2026"; null -> "Present". */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function fmtMonth(value) {
  if (!value) return 'Present';
  const [y, m] = String(value).split('-');
  const idx = Number(m) - 1;
  return MONTHS[idx] ? `${MONTHS[idx]} ${y}` : String(value);
}

export const fmtRange = (start, end) => `${fmtMonth(start)} — ${fmtMonth(end)}`;
