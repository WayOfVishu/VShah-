// What "remote" actually means on a given posting.
//
// The word alone is worth very little. Three different postings all say
// "Remote" in their location field:
//
//   1. Remote anywhere in Canada          — the one worth having
//   2. Remote, but US-only                — needs a TN visa, so effectively closed
//   3. "Remote" that turns out to be      — the description says three days a
//      hybrid                               week in a Toronto office
//
// The location string cannot tell these apart; only the description can. So
// this reads the body, not just the header, and the `remote` bucket in
// scoring.js is gated on the answer.
//
// A note on what this does NOT do: a hybrid posting is not thrown away, it
// just stops counting as *remote*. "Calgary, AB — Hybrid" is still a Calgary
// job and still buckets as Calgary, because hybrid is fine when the office is
// the one you can drive to. It is only hybrid-in-a-city-you-do-not-live-in
// that becomes worthless, and that falls out on its own: with no remote bucket
// to land in, it has only its city to match, which is off-list.

// The location field or flag claims remote at all.
const CLAIMS_REMOTE =
  /\bremote\b|\bwork from home\b|\bwfh\b|\banywhere\b|\bdistributed\b|\btelecommut\w*\b|t[ée]l[ée]travail/i;

// Unambiguous statements that the role is genuinely fully remote. These win
// over a hybrid signal, on the theory that a posting saying "100% remote" and
// also using the word "hybrid" somewhere is describing the company's other
// roles or its general policy, not this job.
const FULLY_REMOTE = [
  /\b(?:100%|fully|entirely|completely)\s*[- ]?\s*remote\b/i,
  /\bremote[- ]?first\b/i,
  /\bremote[- ]?only\b/i,
  /\bwork from anywhere\b/i,
  /\bpermanently remote\b/i,
];

// Signals that an office is actually expected. Deliberately specific: a bare
// "onsite" is not here, because it shows up constantly in unrelated senses
// ("onsite customer visits", "onsite data centre"), and treating that as
// proof of hybrid would quietly delete real remote jobs.
// Note what is NOT here: a bare `\bhybrid\b`. Wealthsimple closes every
// posting with "We are a hybrid team with over 1,500 employees across North
// America" — a sentence about the company's workforce, not about this job —
// and on a bare match that boilerplate disqualified all 37 of their
// genuinely-remote-in-Canada roles. The word only counts when it is attached
// to the working arrangement of the role being advertised.
const HYBRID_SIGNALS = [
  /\bhybrid\s+(?:role|position|job|opportunity|work(?:ing)?|model|schedule|arrangement|setup|policy)\b/i,
  /\b(?:role|position|job)\s+is\s+hybrid\b/i,
  /\bhybrid\s*\(\s*\d+\s*days?/i,
  /\bthis is a hybrid\b/i,
  /\b\d+\s*(?:\+\s*)?days?\s*(?:per|a|each|\/)\s*week\s*(?:in|at|from)\s*(?:the\s*|our\s*)?office\b/i,
  /\bin[- ]office\s*\d+\s*days?\b/i,
  /\b\d+\s*days?\s*in[- ]office\b/i,
  /\bmust\s+(?:be able to\s+)?(?:commute|come in(?:to)?|work from|travel)\s+(?:in\s+)?(?:to\s+)?(?:the\s+|our\s+)?office\b/i,
  /\breturn[- ]to[- ]office\b/i,
  /\bbased\s+(?:in|out of)\s+(?:our|the)\s+[\w\s]{0,30}office\b/i,
  /\bexpected\s+to\s+be\s+on[- ]?site\b/i,
  /\bon[- ]?site\s+presence\s+(?:is\s+)?required\b/i,
  /\brelocation\s+(?:is\s+)?required\b/i,
  /\bmust\s+(?:reside|live)\s+within\s+\d+\s*(?:km|kilometres|kilometers|miles)\b/i,
];

// Where the role may be performed from.
const CANADA_SCOPE = [
  /\bremote\b[^.]{0,40}\bcanada\b/i,
  /\bcanada\b[^.]{0,40}\bremote\b/i,
  /\banywhere in canada\b/i,
  /\b(?:within|across|throughout)\s+canada\b/i,
  /\bcanada[- ]wide\b/i,
  /\bcanadian\s+(?:residents?|applicants?)\b/i,
  /\bmust\s+(?:reside|be located|be based)\s+in\s+canada\b/i,
  /\b(?:eligible|authorized|authorised)\s+to\s+work\s+in\s+canada\b/i,
];

// "US" has to be matched case-sensitively. Lowercase "us" is the pronoun, and
// treating it as a country turned "Remote — Build things with us" into a
// US-fenced posting. Every pattern below is therefore case-SENSITIVE for the
// abbreviation, with spelled-out variants added back where they are safe.
const US = "(?:U\\.S\\.A?|USA?|United States)";
const US_SCOPE = [
  new RegExp(`\\bremote\\b[^.]{0,40}\\b${US}\\b`),
  new RegExp(`\\b${US}[- ]?(?:only|based)\\b`),
  new RegExp(`\\bmust\\s+(?:reside|be located|be based)\\s+in\\s+the\\s+${US}\\b`),
  new RegExp(`\\b(?:eligible|authorized|authorised)\\s+to\\s+work\\s+in\\s+the\\s+${US}\\b`),
  new RegExp(`\\banywhere in the ${US}\\b`),
  /\bmust reside in the united states\b/i,
  /\banywhere in the united states\b/i,
];

const GLOBAL_SCOPE = [
  /\banywhere in the world\b/i,
  /\b(?:work|hire|hiring)\s+(?:from\s+)?(?:anywhere|globally|worldwide)\b/i,
  /\bglobally distributed\b/i,
  /\bany (?:country|location|timezone)\b/i,
];

// Boilerplate a posting has explicitly disowned.
//
// Large employers append a standing block of company-wide policy to every
// posting and then say it does not apply to this one. Anthropic's fellowship
// listings close with "The below are Anthropic's policies for full time roles.
// These do NOT apply to the Fellows Program." and then state a 25%-in-office
// "Location-based hybrid policy" — which matched HYBRID_SIGNALS and turned a
// remote-friendly Canadian posting into a hybrid one, dropping it entirely
// (its only other locations are off-list).
//
// This is the same failure as the Wealthsimple boilerplate noted above, one
// level out: not a word that means something else in context, but a whole
// section the employer has told us to ignore. Text from the disclaimer onward
// is therefore not evidence about *this* role.
const DISCLAIMER = [
  /\bthese\s+do\s+not\s+apply\b/i,
  /\bdo(?:es)?\s+not\s+apply\s+to\s+(?:the\s+)?[\w\s]{0,30}\b(?:program|fellowship|role|position)\b/i,
  /\bthe\s+(?:below|following)\s+are\b[^.]{0,80}\bfor\s+full[- ]?time\s+roles\b/i,
];

// The body up to the first disclaimer. Used only for the hybrid question:
// scope detection still reads the whole posting, because the countries a role
// may be performed from are stated in the live section, and a truncation there
// would lose more than it saved.
export function beforeDisclaimer(body) {
  const text = String(body || "");
  let cut = text.length;
  for (const re of DISCLAIMER) {
    const m = re.exec(text);
    if (m && m.index < cut) cut = m.index;
  }
  return text.slice(0, cut);
}

const anyMatch = (patterns, text) => patterns.some((re) => re.test(text));
const firstMatch = (patterns, text) => patterns.find((re) => re.test(text));

// Canada is checked before the US on purpose. "Remote — Canada or US" is a
// job he can take from Calgary; the presence of the US does not disqualify it.
// Only a posting that names the US and never names Canada is US-fenced.
function detectScope(text) {
  if (anyMatch(CANADA_SCOPE, text) || /\bcanada\b/i.test(text)) return "canada";
  if (anyMatch(US_SCOPE, text)) return "us";
  if (anyMatch(GLOBAL_SCOPE, text)) return "global";
  return "unknown";
}

// The full picture for one posting. `reasons` carries the evidence so a
// surprising verdict can be traced to the phrase that caused it rather than
// argued with.
export function classifyRemote(job) {
  const header = [job.location, job.remote_status].filter(Boolean).join(" ");
  const body = String(job.description || "");
  const all = `${header}\n${body}`;

  const claimsRemote = CLAIMS_REMOTE.test(header) || anyMatch(FULLY_REMOTE, body);
  const reasons = [];

  const fullyRemoteHit = firstMatch(FULLY_REMOTE, all);
  // "Hybrid" in the location field is always about this role — that field is
  // the employer's structured statement of where the job is. In the body it
  // has to be attached to the role (see HYBRID_SIGNALS) to count.
  const hybridHit = /\bhybrid\b/i.test(header)
    ? /\bhybrid\b/i
    : firstMatch(HYBRID_SIGNALS, beforeDisclaimer(body));

  // An explicit "fully remote" outranks an incidental "hybrid" elsewhere in
  // the body; otherwise any hybrid signal settles it.
  let isHybrid = false;
  if (hybridHit && !fullyRemoteHit) {
    isHybrid = true;
    reasons.push(`hybrid signal: ${hybridHit.source}`);
  } else if (hybridHit && fullyRemoteHit) {
    reasons.push("says fully remote despite a hybrid mention; treated as remote");
  }

  const scope = detectScope(all);
  reasons.push(`scope: ${scope}`);

  // Unknown scope still qualifies. A Canadian company's posting that just says
  // "Remote" is far more often Canada-eligible than not, and excluding it
  // would cost more real jobs than the US noise it would remove. The existing
  // unsponsored-US penalty in scoring.js still demotes the ones that smell
  // American, so they stay visible and flagged rather than silently deleted.
  const qualifies = claimsRemote && !isHybrid && scope !== "us";

  return { claimsRemote, isHybrid, scope, qualifies, reasons };
}

// The single question scoring.js asks: may this posting occupy the `remote`
// bucket?
export function isTrulyRemote(job) {
  return classifyRemote(job).qualifies;
}
