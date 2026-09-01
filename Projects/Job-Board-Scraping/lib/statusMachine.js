// PRD req. 21: "This state machine, not just 'there's a confirm button', is
// the actual approval gate." So the legal transitions live here as data, in
// one place, rather than being implied by whichever endpoint happens to run —
// an endpoint that forgets to check is how `new` quietly reaches `tailored`
// without a confirmation, which PRD §8 lists as a hard success metric.
//
// Not in Tasks.md's original file list; extracted for the same reason
// lib/sourceHealth.js was — it needs to be independently testable, and both
// server.js and lib/tailorInvoke.js enforce the same rules.

export const STATUSES = [
  "new",
  "queued",
  "generating",
  "tailored",
  "rejected",
  "dismissed",
  "applied",
  "archived",
];

// Keyed by current status -> the set it may legally move to.
export const TRANSITIONS = {
  // req. 20: marking a row for tailoring is what sets `queued`.
  // `applied` is reachable directly because req. 32 lists mark-applied as a
  // plain row action — the user may apply to a posting without ever asking
  // for a tailored resume, and the Discovered view must not force them
  // through the tailoring flow to log that.
  new: ["queued", "dismissed", "archived", "applied"],
  // req. 21: user confirms -> generating; or rejects; or edits and re-queues.
  queued: ["generating", "rejected", "queued", "dismissed", "new", "applied"],
  // req. 21/28: success -> tailored, failure -> back to queued (never `new`).
  generating: ["tailored", "queued"],
  // req. 32: a tailored draft can be applied, set aside, or re-tailored.
  tailored: ["applied", "dismissed", "queued"],
  // req. 21: rejected is terminal *unless manually reset*.
  rejected: ["new"],
  dismissed: ["new"],
  // req. 32: applied is the end of this system's involvement (req. 29).
  applied: [],
  // req. 16: archived rows stay queryable and can be pulled back.
  archived: ["new", "dismissed"],
};

// Transitions a user is allowed to trigger directly from the dashboard.
// `generating` and `tailored` are deliberately absent: the only way into them
// is through lib/tailorInvoke.js, so no dashboard action can reach `tailored`
// without going through the confirmation + generation path (PRD §8).
export const USER_TRIGGERABLE = ["queued", "rejected", "dismissed", "applied", "new", "archived"];

export class TransitionError extends Error {
  constructor(from, to) {
    super(`Illegal status transition: ${from} -> ${to}`);
    this.name = "TransitionError";
    this.from = from;
    this.to = to;
    this.statusCode = 409;
  }
}

export function canTransition(from, to) {
  return Boolean(TRANSITIONS[from]?.includes(to));
}

export function assertTransition(from, to) {
  if (!STATUSES.includes(to)) throw new TransitionError(from, to);
  if (!canTransition(from, to)) throw new TransitionError(from, to);
}

// Applies a transition to one discovered_jobs row inside the caller's db.
// Returns the updated row. `extra` sets additional columns in the same
// statement (resume_path on `tailored`, tailor_error on the req. 28 fallback)
// so a row can never be left half-transitioned.
export function transition(db, id, to, extra = {}) {
  const row = db.prepare("SELECT id, status FROM discovered_jobs WHERE id = ?").get(id);
  if (!row) {
    const err = new Error(`Discovered job ${id} not found`);
    err.statusCode = 404;
    throw err;
  }
  assertTransition(row.status, to);

  const cols = ["status = @status"];
  for (const key of Object.keys(extra)) cols.push(`${key} = @${key}`);
  db.prepare(`UPDATE discovered_jobs SET ${cols.join(", ")} WHERE id = @id`).run({
    id,
    status: to,
    ...extra,
  });
  return db.prepare("SELECT * FROM discovered_jobs WHERE id = ?").get(id);
}
