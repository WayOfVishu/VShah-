"""Remote-work classifier — a faithful Python port of the Jobs Web App's
``lib/remote.js``, so the demo on the portfolio runs the real decision logic
rather than a canned imitation of it.

The point of the demo is the *evidence*: every verdict comes back with the
phrase that caused it, its offset in the source text, and which field it came
from. A surprising verdict should be traceable, not arguable.

Kept deliberately in lockstep with the JS original. If the rules change there,
change them here too — the patterns below are the contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Scope = Literal["canada", "us", "global", "unknown"]

# The location field or flag claims remote at all.
CLAIMS_REMOTE = re.compile(
    r"\bremote\b|\bwork from home\b|\bwfh\b|\banywhere\b|\bdistributed\b"
    r"|\btelecommut\w*\b|t[ée]l[ée]travail",
    re.I,
)

# Unambiguous statements that the role is genuinely fully remote. These win
# over a hybrid signal, on the theory that a posting saying "100% remote" and
# also using the word "hybrid" somewhere is describing the company's other
# roles or its general policy, not this job.
FULLY_REMOTE = [
    re.compile(r"\b(?:100%|fully|entirely|completely)\s*[- ]?\s*remote\b", re.I),
    re.compile(r"\bremote[- ]?first\b", re.I),
    re.compile(r"\bremote[- ]?only\b", re.I),
    re.compile(r"\bwork from anywhere\b", re.I),
    re.compile(r"\bpermanently remote\b", re.I),
]

# Signals that an office is actually expected. Deliberately specific: a bare
# "onsite" is not here, because it shows up constantly in unrelated senses
# ("onsite customer visits", "onsite data centre"), and treating that as proof
# of hybrid would quietly delete real remote jobs.
#
# Note what is NOT here: a bare \bhybrid\b. One employer closes every posting
# with "We are a hybrid team with over 1,500 employees across North America" —
# a sentence about the company's workforce, not about this job — and on a bare
# match that boilerplate disqualified all 37 of their genuinely-remote-in-
# Canada roles. The word only counts when it is attached to the working
# arrangement of the role being advertised.
HYBRID_SIGNALS = [
    re.compile(
        r"\bhybrid\s+(?:role|position|job|opportunity|work(?:ing)?|model|schedule"
        r"|arrangement|setup|policy)\b",
        re.I,
    ),
    re.compile(r"\b(?:role|position|job)\s+is\s+hybrid\b", re.I),
    re.compile(r"\bhybrid\s*\(\s*\d+\s*days?", re.I),
    re.compile(r"\bthis is a hybrid\b", re.I),
    re.compile(
        r"\b\d+\s*(?:\+\s*)?days?\s*(?:per|a|each|/)\s*week\s*(?:in|at|from)"
        r"\s*(?:the\s*|our\s*)?office\b",
        re.I,
    ),
    re.compile(r"\bin[- ]office\s*\d+\s*days?\b", re.I),
    re.compile(r"\b\d+\s*days?\s*in[- ]office\b", re.I),
    re.compile(
        r"\bmust\s+(?:be able to\s+)?(?:commute|come in(?:to)?|work from|travel)"
        r"\s+(?:in\s+)?(?:to\s+)?(?:the\s+|our\s+)?office\b",
        re.I,
    ),
    re.compile(r"\breturn[- ]to[- ]office\b", re.I),
    re.compile(r"\bbased\s+(?:in|out of)\s+(?:our|the)\s+[\w\s]{0,30}office\b", re.I),
    re.compile(r"\bexpected\s+to\s+be\s+on[- ]?site\b", re.I),
    re.compile(r"\bon[- ]?site\s+presence\s+(?:is\s+)?required\b", re.I),
    re.compile(r"\brelocation\s+(?:is\s+)?required\b", re.I),
    re.compile(
        r"\bmust\s+(?:reside|live)\s+within\s+\d+\s*"
        r"(?:km|kilometres|kilometers|miles)\b",
        re.I,
    ),
]

# Where the role may be performed from.
CANADA_SCOPE = [
    re.compile(r"\bremote\b[^.]{0,40}\bcanada\b", re.I),
    re.compile(r"\bcanada\b[^.]{0,40}\bremote\b", re.I),
    re.compile(r"\banywhere in canada\b", re.I),
    re.compile(r"\b(?:within|across|throughout)\s+canada\b", re.I),
    re.compile(r"\bcanada[- ]wide\b", re.I),
    re.compile(r"\bcanadian\s+(?:residents?|applicants?)\b", re.I),
    re.compile(r"\bmust\s+(?:reside|be located|be based)\s+in\s+canada\b", re.I),
    re.compile(r"\b(?:eligible|authorized|authorised)\s+to\s+work\s+in\s+canada\b", re.I),
]

# "US" has to be matched case-sensitively. Lowercase "us" is the pronoun, and
# treating it as a country turned "Remote — Build things with us" into a
# US-fenced posting. Every pattern below is therefore case-SENSITIVE for the
# abbreviation, with spelled-out variants added back where they are safe.
_US = r"(?:U\.S\.A?|USA?|United States)"
US_SCOPE = [
    re.compile(rf"\bremote\b[^.]{{0,40}}\b{_US}\b"),
    re.compile(rf"\b{_US}[- ]?(?:only|based)\b"),
    re.compile(rf"\bmust\s+(?:reside|be located|be based)\s+in\s+the\s+{_US}\b"),
    re.compile(rf"\b(?:eligible|authorized|authorised)\s+to\s+work\s+in\s+the\s+{_US}\b"),
    re.compile(rf"\banywhere in the {_US}\b"),
    re.compile(r"\bmust reside in the united states\b", re.I),
    re.compile(r"\banywhere in the united states\b", re.I),
]

GLOBAL_SCOPE = [
    re.compile(r"\banywhere in the world\b", re.I),
    re.compile(r"\b(?:work|hire|hiring)\s+(?:from\s+)?(?:anywhere|globally|worldwide)\b", re.I),
    re.compile(r"\bglobally distributed\b", re.I),
    re.compile(r"\bany (?:country|location|timezone)\b", re.I),
]

_CANADA_BARE = re.compile(r"\bcanada\b", re.I)
_HYBRID_BARE = re.compile(r"\bhybrid\b", re.I)


@dataclass
class Evidence:
    """One matched phrase, with enough context for the UI to highlight it."""

    kind: str           # claims | fully_remote | hybrid | scope_canada | scope_us | scope_global
    pattern: str
    match: str
    where: str          # "header" | "description"
    start: int
    end: int

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "pattern": self.pattern,
            "match": self.match,
            "where": self.where,
            "start": self.start,
            "end": self.end,
        }


@dataclass
class Gate:
    id: str
    label: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "passed": self.passed, "detail": self.detail}


@dataclass
class Classification:
    claims_remote: bool
    is_hybrid: bool
    scope: Scope
    qualifies: bool
    verdict: str
    headline: str
    reasons: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    gates: list[Gate] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "claimsRemote": self.claims_remote,
            "isHybrid": self.is_hybrid,
            "scope": self.scope,
            "qualifies": self.qualifies,
            "verdict": self.verdict,
            "headline": self.headline,
            "reasons": self.reasons,
            "evidence": [e.as_dict() for e in self.evidence],
            "gates": [g.as_dict() for g in self.gates],
        }


def _first_match(patterns: list[re.Pattern], text: str) -> tuple[re.Pattern, re.Match] | None:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return pat, m
    return None


def _detect_scope(text: str) -> tuple[Scope, tuple[re.Pattern, re.Match] | None]:
    """Canada is checked before the US on purpose. "Remote — Canada or US" is a
    job you can take from Calgary; the presence of the US does not disqualify
    it. Only a posting that names the US and never names Canada is US-fenced.
    """
    hit = _first_match(CANADA_SCOPE, text)
    if hit:
        return "canada", hit
    bare = _CANADA_BARE.search(text)
    if bare:
        return "canada", (_CANADA_BARE, bare)

    hit = _first_match(US_SCOPE, text)
    if hit:
        return "us", hit

    hit = _first_match(GLOBAL_SCOPE, text)
    if hit:
        return "global", hit

    return "unknown", None


def classify_remote(location: str = "", remote_status: str = "", description: str = "") -> Classification:
    """The full picture for one posting.

    ``reasons`` and ``evidence`` carry the proof, so a surprising verdict can be
    traced to the phrase that caused it.
    """
    header = " ".join(p for p in (location, remote_status) if p)
    body = description or ""
    combined = f"{header}\n{body}"
    header_len = len(header) + 1  # +1 for the newline, to map offsets back

    evidence: list[Evidence] = []
    reasons: list[str] = []

    def add(kind: str, pat: re.Pattern, m: re.Match, source: str) -> None:
        if source == "combined":
            where = "header" if m.start() < header_len - 1 else "description"
            start = m.start() if where == "header" else m.start() - header_len
            end = m.end() if where == "header" else m.end() - header_len
        else:
            where = source
            start, end = m.start(), m.end()
        evidence.append(Evidence(kind, pat.pattern, m.group(0), where, max(start, 0), max(end, 0)))

    # --- gate 1: does it claim remote at all? -----------------------------
    claims_hit = CLAIMS_REMOTE.search(header)
    fully_body = _first_match(FULLY_REMOTE, body)
    claims_remote = bool(claims_hit) or bool(fully_body)

    if claims_hit:
        add("claims", CLAIMS_REMOTE, claims_hit, "header")
    if fully_body:
        add("fully_remote", fully_body[0], fully_body[1], "description")

    # --- gate 2: is it secretly hybrid? -----------------------------------
    fully_any = _first_match(FULLY_REMOTE, combined)

    # "Hybrid" in the location field is always about this role — that field is
    # the employer's structured statement of where the job is. In the body it
    # has to be attached to the role (see HYBRID_SIGNALS) to count.
    header_hybrid = _HYBRID_BARE.search(header)
    if header_hybrid:
        hybrid_hit: tuple[re.Pattern, re.Match] | None = (_HYBRID_BARE, header_hybrid)
        hybrid_where = "header"
    else:
        hybrid_hit = _first_match(HYBRID_SIGNALS, body)
        hybrid_where = "description"

    is_hybrid = False
    if hybrid_hit and not fully_any:
        is_hybrid = True
        add("hybrid", hybrid_hit[0], hybrid_hit[1], hybrid_where)
        reasons.append(f"hybrid signal: {hybrid_hit[0].pattern}")
    elif hybrid_hit and fully_any:
        add("hybrid", hybrid_hit[0], hybrid_hit[1], hybrid_where)
        reasons.append("says fully remote despite a hybrid mention; treated as remote")

    # --- gate 3: where may it be performed from? --------------------------
    scope, scope_hit = _detect_scope(combined)
    if scope_hit:
        add(f"scope_{scope}", scope_hit[0], scope_hit[1], "combined")
    reasons.append(f"scope: {scope}")

    # Unknown scope still qualifies. A Canadian company's posting that just
    # says "Remote" is far more often Canada-eligible than not, and excluding
    # it would cost more real jobs than the US noise it would remove. The
    # unsponsored-US penalty in scoring still demotes the ones that smell
    # American, so they stay visible and flagged rather than silently deleted.
    qualifies = claims_remote and not is_hybrid and scope != "us"

    # Gate details are read by a human on the site, so they say what matched in
    # plain language. The raw pattern stays in `reasons`, which is for me.
    if is_hybrid:
        field = "location field" if hybrid_where == "header" else "description"
        hybrid_detail = f'the {field} says "{hybrid_hit[1].group(0)}" about this role'
    elif hybrid_hit:
        hybrid_detail = 'says fully remote despite mentioning hybrid, so the hybrid mention is ignored'
    else:
        hybrid_detail = 'nothing attaches "hybrid" to the role itself'

    gates = [
        Gate(
            "claims",
            "Claims remote",
            claims_remote,
            "matched a remote claim in the location field"
            if claims_hit
            else ("description states it is fully remote" if fully_body else "nothing claims remote"),
        ),
        Gate("hybrid", "Not secretly hybrid", not is_hybrid, hybrid_detail),
        Gate(
            "scope",
            "Not US-fenced",
            scope != "us",
            f"scope resolved to {scope}",
        ),
    ]

    if qualifies:
        verdict, headline = "qualifies", "Occupies the remote bucket"
    elif is_hybrid:
        verdict, headline = "hybrid", "Hybrid — keeps its city, loses the remote bucket"
    elif scope == "us":
        verdict, headline = "us-fenced", "US-fenced — needs a TN visa, effectively closed"
    else:
        verdict, headline = "not-remote", "Does not claim remote"

    return Classification(
        claims_remote=claims_remote,
        is_hybrid=is_hybrid,
        scope=scope,
        qualifies=qualifies,
        verdict=verdict,
        headline=headline,
        reasons=reasons,
        evidence=evidence,
        gates=gates,
    )


# Worked examples, each chosen because it breaks a naive implementation.
SAMPLES = [
    {
        "id": "boilerplate-trap",
        "label": "The boilerplate trap",
        "note": "A bare match on the word 'hybrid' fails all 37 of this employer's genuinely remote roles.",
        "location": "Remote - Canada",
        "remote_status": "remote",
        "description": (
            "We are looking for a Machine Learning Engineer to join our data platform "
            "team. You will own ingestion pipelines end to end.\n\n"
            "We are a hybrid team with over 1,500 employees across North America."
        ),
    },
    {
        "id": "genuinely-hybrid",
        "label": "Genuinely hybrid",
        "note": "The description overrules a location field that says Remote.",
        "location": "Remote",
        "remote_status": "remote",
        "description": (
            "This is a hybrid role. You will be expected in the Toronto office "
            "3 days per week in office, with the remainder worked from home."
        ),
    },
    {
        "id": "us-fenced",
        "label": "US-fenced",
        "note": "Remote, but closed in practice without a TN visa.",
        "location": "Remote - US",
        "remote_status": "remote",
        "description": "Fully remote within the United States. Must reside in the United States.",
    },
    {
        "id": "pronoun-trap",
        "label": "The pronoun trap",
        "note": "Lowercase 'us' is a pronoun. Case-sensitive matching is what saves this one.",
        "location": "Remote",
        "remote_status": "remote",
        "description": "Remote - come build great things with us. Open to applicants across Canada.",
    },
    {
        "id": "canada-or-us",
        "label": "Canada or US",
        "note": "Naming the US alongside Canada is fine; only a US-and-never-Canada posting is fenced.",
        "location": "Remote - Canada or US",
        "remote_status": "remote",
        "description": "Work from anywhere in Canada or the United States.",
    },
    {
        "id": "hybrid-in-calgary",
        "label": "Hybrid in Calgary",
        "note": "Still a Calgary job. Hybrid only hurts when the office is one you cannot drive to.",
        "location": "Calgary, AB - Hybrid",
        "remote_status": "",
        "description": "Hybrid role, 2 days per week in the office in downtown Calgary.",
    },
]
