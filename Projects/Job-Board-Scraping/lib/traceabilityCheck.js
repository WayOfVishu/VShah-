// PRD req. 23: the concrete, post-generation enforcement of "reorder and
// rephrase, never invent." Every substantive line of a tailored draft is
// scored against the base resume; anything below threshold is flagged for the
// user rather than silently accepted or silently blocked.
//
// PRD §7 is explicit that this starts as a cheap deterministic heuristic, not
// a second LLM call — the whole point of the gate is that it's fast and free.
//
// Two independent checks, because they catch different failure modes:
//   1. Token overlap (unigram coverage + bigram phrasing bonus) catches a line
//      built out of vocabulary that isn't in the base resume at all — a whole
//      invented job, skill, or credential.
//   2. Numeric support catches the case overlap is blind to: a line made
//      entirely of the resume's own words with one number changed ("40%" ->
//      "65%"). req. 23 names dates and metrics specifically, and a swapped
//      metric scores ~1.0 on overlap alone.

const DEFAULT_THRESHOLD = 0.55;

// Words that carry no traceability signal — a tailored line sharing only
// these with the base resume has not actually been traced to anything.
const STOPWORDS = new Set(
  ("a an and are as at be by for from has have in into is it its of on or that the to " +
    "with using used within across via while over under after before during each " +
    "including include includes than then this these those their they we our my i " +
    "also both such other more most new work working").split(" ")
);

// Crude suffix stemming. Not linguistically correct, and doesn't need to be —
// it exists so "trigger"/"triggering" and "pipeline"/"pipelines" count as the
// same evidence, which is the difference between a false flag and a pass.
// The suffix order matters: strip the plural/verb ending first, then a
// trailing "e". Without the second step "pipelines" conflates to "pipelin"
// while "pipeline" stays whole, and the two never match — which is the exact
// false flag stemming exists to prevent.
function stripSuffix(token) {
  if (token.length > 4 && token.endsWith("ies")) return `${token.slice(0, -3)}y`; // companies -> company
  if (token.length > 4 && token.endsWith("sses")) return token.slice(0, -2);      // classes -> class
  if (token.length > 5 && /(?:[sxz]|ch|sh)es$/.test(token)) return token.slice(0, -2); // boxes -> box
  for (const suffix of ["ingly", "ing", "edly", "ed", "es", "s"]) {
    if (token.endsWith(suffix) && token.length - suffix.length >= 4) {
      // Don't turn "class" into "clas".
      if (suffix === "s" && token.endsWith("ss")) return token;
      return token.slice(0, token.length - suffix.length);
    }
  }
  return token;
}

function stem(token) {
  // Leave technical tokens alone: stripping the "s" off "node.js" or the "ed"
  // off a version string produces junk, and they carry the strongest
  // traceability signal of anything in a resume.
  if (token.length <= 4 || /[0-9./+#]/.test(token)) return token;
  const stripped = stripSuffix(token);
  // Drop a trailing silent "e" so consolidate / consolidating / consolidated
  // and pipeline / pipelines all land on the same stem.
  return stripped.length > 4 && stripped.endsWith("e") ? stripped.slice(0, -1) : stripped;
}

export function tokenize(text) {
  const raw = String(text || "")
    .toLowerCase()
    // Keep intra-word hyphens/dots/plus/slash (k8s, ci/cd, c++, node.js, 100k+)
    .replace(/[^a-z0-9+#./-]+/g, " ")
    .split(/\s+/)
    .map((t) => t.replace(/^[-./]+|[-./]+$/g, ""))
    .filter((t) => t.length > 1 && !STOPWORDS.has(t));

  const out = [];
  for (const token of raw) {
    out.push(stem(token));
    // A compound written as one hyphenated token in the draft but as separate
    // words in the base resume (frame-difference vs "frame difference") is the
    // same claim; emit the parts too so it matches either way.
    if (token.includes("-")) {
      for (const part of token.split("-")) {
        if (part.length > 1 && !STOPWORDS.has(part)) out.push(stem(part));
      }
    }
  }
  return out;
}

function bigrams(tokens) {
  const out = new Set();
  for (let i = 0; i < tokens.length - 1; i++) out.add(`${tokens[i]} ${tokens[i + 1]}`);
  return out;
}

// Every number a line asserts, normalized so "40%", "40 %" and "40" compare
// equal. Ranges ("60-70%") yield both endpoints. Ordinary list scaffolding
// numbers are not excluded — a resume line's numbers are nearly always claims.
function numericClaims(text) {
  const out = new Set();
  const matches = String(text || "").match(/\d[\d,.]*\s*(?:%|k\+?|m\+?|b\+?|x)?/gi) || [];
  for (const m of matches) {
    const norm = m.toLowerCase().replace(/[\s,]/g, "").replace(/\.$/, "");
    out.add(norm);
    out.add(norm.replace(/[^0-9.]/g, "")); // bare digits, so "40%" also matches "40"
  }
  out.delete("");
  return out;
}

// Markdown hard-wraps a paragraph or bullet across several physical lines, so
// a raw line is usually a fragment rather than a claim. Scoring fragments
// produces false flags on continuation lines ("deployed on Kubernetes.
// Comfortable taking an...") while letting a fabricated clause hide inside an
// otherwise-traceable one. Regroup the physical lines into logical blocks
// first, remembering the line each block starts on.
function toBlocks(text) {
  const blocks = [];
  let current = null;

  String(text || "")
    .split(/\r?\n/)
    .forEach((raw, i) => {
      const line = raw.trim();
      const isBlank = line === "";
      const startsNewBlock = /^(?:[-*+]\s|\d+[.)]\s|#{1,6}\s|>\s)/.test(line) || /^\|/.test(line);

      if (isBlank) {
        current = null;
        return;
      }
      if (startsNewBlock || !current) {
        current = { line: i + 1, text: line };
        blocks.push(current);
      } else {
        current.text += ` ${line}`; // a wrapped continuation of the block above
      }
    });

  return blocks;
}

// One claim per sentence. A bullet may hold several; a fabricated clause
// appended to a true one must not be diluted by the true half's score.
function toClaims(text) {
  const claims = [];
  for (const block of toBlocks(text)) {
    const body = block.text.replace(/^(?:[-*+]|\d+[.)])\s+/, "").replace(/^#{1,6}\s+/, "");
    // Don't split on the periods inside "Node.js", "5.5%", or "e.g."
    const sentences = body.split(/(?<=[.!?])\s+(?=[A-Z(])/);
    for (const sentence of sentences) {
      if (sentence.trim()) claims.push({ line: block.line, text: sentence.trim() });
    }
  }
  return claims;
}

// Markdown scaffolding a tailored draft legitimately adds (headings the base
// resume also has, bullets, rules). Lines that are pure structure aren't
// claims about the candidate, so scoring them just produces noise.
function isSubstantive(line) {
  const stripped = line.replace(/^[\s>*+-]*/, "").replace(/^#+\s*/, "").replace(/[*_`]/g, "").trim();
  if (stripped.length < 25) return false;         // headings, section labels, dates
  if (/^-{3,}$|^={3,}$|^\|/.test(stripped)) return false; // rules and table rows
  return tokenize(stripped).length >= 4;
}

// Score one line 0..1 against the base resume's token/bigram sets.
function scoreLine(tokens, baseTokens, baseBigrams) {
  if (tokens.length === 0) return 1;

  const covered = tokens.filter((t) => baseTokens.has(t)).length;
  const unigram = covered / tokens.length;

  const lineBigrams = [...bigrams(tokens)];
  const bigramHit = lineBigrams.length
    ? lineBigrams.filter((b) => baseBigrams.has(b)).length / lineBigrams.length
    : 0;

  // Unigram coverage is the floor; intact phrasing from the base resume pulls
  // the score up. Weighted 0.75/0.25 so a line can still pass on vocabulary
  // alone when it has been genuinely rephrased (which the prompt invites).
  return Math.min(1, unigram * 0.75 + bigramHit * 0.25 + (unigram >= 0.95 ? 0.05 : 0));
}

// Returns { threshold, flagged, lines, checked, passed }.
// `flagged` holds only the below-threshold lines, in document order, with the
// line number and a `reason` so the dashboard can highlight them against the
// base resume (PRD §6 Design Considerations).
export function checkTraceability(draftText, baseResumeText, opts = {}) {
  const threshold = opts.threshold ?? DEFAULT_THRESHOLD;
  const baseTokenList = tokenize(baseResumeText);
  const baseTokens = new Set(baseTokenList);
  const baseBigrams = bigrams(baseTokenList);
  const baseNumbers = numericClaims(baseResumeText);

  const lines = [];
  toClaims(draftText)
    .forEach(({ line: lineNumber, text: raw }) => {
      if (!isSubstantive(raw)) return;
      const score = Number(scoreLine(tokenize(raw), baseTokens, baseBigrams).toFixed(3));
      const unsupportedNumbers = [...numericClaims(raw)].filter(
        (n) => !baseNumbers.has(n) && !/^(19|20)\d{2}$/.test(n) // bare years come from date headers
      );
      // A number is only "unsupported" if neither its formatted nor its bare
      // form is in the base resume; numericClaims emits both, so require the
      // bare form to be missing too before flagging.
      const badNumbers = unsupportedNumbers.filter((n) => !baseNumbers.has(n.replace(/[^0-9.]/g, "")));

      const reasons = [];
      if (score < threshold) reasons.push("low-overlap");
      if (badNumbers.length > 0) reasons.push("unsupported-number");

      lines.push({
        line: lineNumber,
        text: raw.trim(),
        score,
        unsupportedNumbers: badNumbers,
        reasons,
        flagged: reasons.length > 0,
      });
    });

  return {
    threshold,
    lines,
    flagged: lines.filter((l) => l.flagged),
    checked: lines.length,
    passed: lines.every((l) => !l.flagged),
  };
}
