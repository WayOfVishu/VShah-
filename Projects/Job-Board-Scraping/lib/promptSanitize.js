// PRD req. 24: scraped job-description text is untrusted input. Before it is
// interpolated into the tailoring prompt it gets run through here, which
// neutralizes instruction-like patterns and wraps the remainder in explicit
// delimiters marking it as data to read, not instructions to follow.
//
// Deliberately a small pure function (PRD §7) so the injected-text fixture
// test in promptSanitize.test.js can assert on it directly, rather than
// having to drive the whole tailoring script.

export const DATA_FENCE_OPEN = "<<<JOB_POSTING_DATA";
export const DATA_FENCE_CLOSE = "JOB_POSTING_DATA>>>";
export const REDACTION = "[REDACTED-INSTRUCTION]";

// Each rule is `[name, regex]`. Regexes are case-insensitive and global so a
// posting that repeats an attempt gets every occurrence neutralized, not just
// the first. Ordering doesn't matter — every rule runs over the whole text.
const INSTRUCTION_PATTERNS = [
  // "ignore previous instructions" and its usual rephrasings
  ["override-instructions",
    /\b(?:ignore|disregard|forget|override|bypass|skip)\b[^.\n]{0,40}?\b(?:above|prior|previous|earlier|prec(?:eding|edent)|all|any|original|system|initial)\b[^.\n]{0,40}?\b(?:instruction|instructions|prompt|prompts|rule|rules|direction|directions|context|guideline|guidelines)\b/gi],
  // "new instructions:", "updated instructions follow"
  ["replacement-instructions",
    /\b(?:new|updated|revised|real|actual|true)\s+(?:instruction|instructions|prompt|prompts|task|directive|directives)\b\s*:?/gi],
  // chat-role markers used to fake a turn boundary
  ["role-marker",
    /(?:^|\n)\s*(?:\[|\(|<|##\s*)?\s*(?:system|assistant|user|human|developer)\s*(?:\]|\)|>)?\s*:/gi],
  // model-specific turn tokens
  ["turn-token",
    /<\|[^>\n]{0,40}\|>|<\/?(?:system|assistant|user|human)>/gi],
  // persona hijacking
  ["persona-reset",
    /\byou\s+(?:are|must\s+act|should\s+act|will\s+act|shall\s+act)\s+(?:now\s+)?(?:a|an|as)\b[^.\n]{0,60}/gi],
  // prompt exfiltration
  ["prompt-exfiltration",
    /\b(?:print|output|reveal|repeat|show|display|echo)\b[^.\n]{0,30}?\b(?:system\s+prompt|your\s+(?:prompt|instructions)|the\s+(?:prompt|instructions))\b/gi],
  // direct attempts to steer the resume content itself
  ["fabrication-directive",
    /\b(?:add|insert|include|invent|fabricate|claim|state)\b[^.\n]{0,40}?\b(?:experience|skills?|years?|degree|certification|qualification)s?\b[^.\n]{0,40}?\b(?:not|even\s+if|regardless|whether)\b[^.\n]{0,40}/gi],
  // our own fence, so posting text can't break out of the data block
  ["fence-escape",
    new RegExp(`${DATA_FENCE_OPEN}|${DATA_FENCE_CLOSE}`, "g")],
];

// Strips/neutralizes instruction-like patterns. Returns the cleaned text plus
// the list of rule names that fired, so the confirmation preview (req. 22) can
// tell the user *that* something was scrubbed rather than silently changing
// the posting behind their back.
// Most Tier 1 boards return the description as an HTML blob. Left as-is it
// wastes prompt space, makes the req. 22 preview unreadable, and — the real
// reason this lives in the sanitizer rather than a formatting helper — gives
// an injection somewhere to hide: an HTML comment or a title attribute is
// invisible in a rendered preview but is still text to the model. Strip the
// markup to plain text *first*, so the instruction rules below see everything.
function htmlToText(html) {
  if (!/<[a-z!/]/i.test(html)) return html; // already plain text
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, " ")
    .replace(/<\/(p|div|li|tr|h[1-6]|blockquote)>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<li\b[^>]*>/gi, "\n- ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&#(\d+);/g, (_, d) => String.fromCharCode(Number(d)))
    .replace(/[ \t]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n");
}

export function sanitizePostingText(raw) {
  const original = typeof raw === "string" ? raw : "";
  let text = htmlToText(original)
    // Zero-width and bidi-override characters: invisible in the preview the
    // user approves, but still tokens to the model.
    .replace(/[​-‏‪-‮⁠-⁤﻿]/g, "")
    // Collapse runaway blank lines so a posting can't push the real
    // instructions out of view in the preview.
    .replace(/\n{4,}/g, "\n\n\n");

  const triggered = [];
  for (const [name, pattern] of INSTRUCTION_PATTERNS) {
    // Detect against the raw input as well as the working text. A payload
    // hidden in an HTML comment or a title attribute is already gone by now —
    // htmlToText dropped it — but the user should still be told their posting
    // contained one, rather than having it silently disappear from a preview
    // whose whole purpose (req. 22) is showing them what is going on.
    pattern.lastIndex = 0;
    const inText = pattern.test(text);
    pattern.lastIndex = 0;
    const inRaw = pattern.test(original);
    if (!inText && !inRaw) continue;

    triggered.push(name);
    if (!inText) continue; // nothing left in the working text to redact
    pattern.lastIndex = 0;
    text = text.replace(pattern, (match) => (match.startsWith("\n") ? `\n${REDACTION}` : REDACTION));
  }

  // `triggered` is the security signal (an injection rule fired); `modified`
  // just means the text changed at all, which HTML stripping alone will do.
  // The preview distinguishes them — "we reformatted this" is not a warning.
  return {
    text: text.trim(),
    triggered,
    htmlStripped: /<[a-z!/]/i.test(original),
    modified: triggered.length > 0 || text.trim() !== original.trim(),
  };
}

// Wraps already-sanitized text in the explicit data fence (req. 24). Kept
// separate from sanitizePostingText so the fence is applied exactly once, at
// prompt-assembly time, and the sanitizer stays a pure text->text function.
export function wrapAsData(label, text) {
  return `${DATA_FENCE_OPEN} name="${label}"\n${text}\n${DATA_FENCE_CLOSE}`;
}
