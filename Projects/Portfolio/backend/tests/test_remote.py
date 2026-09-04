"""Tests for the remote classifier port.

The expected values here are not invented: they are the output of the original
``lib/remote.js`` run over the same inputs. If a change makes one of these fail,
the port has drifted from the JavaScript it is supposed to mirror.
"""

import pytest

from app.demos.remote import SAMPLES, classify_remote

# (id, scope, is_hybrid, qualifies) — taken from the JS original.
PARITY = [
    ("boilerplate-trap", "canada", False, True),
    ("genuinely-hybrid", "unknown", True, False),
    ("us-fenced", "us", False, False),
    ("pronoun-trap", "canada", False, True),
    ("canada-or-us", "canada", False, True),
    ("hybrid-in-calgary", "unknown", True, False),
]


def _sample(sample_id):
    return next(s for s in SAMPLES if s["id"] == sample_id)


@pytest.mark.parametrize("sample_id,scope,is_hybrid,qualifies", PARITY)
def test_matches_javascript_original(sample_id, scope, is_hybrid, qualifies):
    s = _sample(sample_id)
    r = classify_remote(s["location"], s["remote_status"], s["description"])
    assert r.scope == scope
    assert r.is_hybrid is is_hybrid
    assert r.qualifies is qualifies


def test_company_boilerplate_does_not_disqualify():
    """The whole point of the deep-dive: a sentence about the company's
    workforce is not a statement about this role."""
    r = classify_remote(
        location="Remote - Canada",
        remote_status="remote",
        description="We are a hybrid team with over 1,500 employees across North America.",
    )
    assert r.is_hybrid is False
    assert r.qualifies is True


def test_hybrid_in_location_field_always_counts():
    """The location field is the employer's structured statement about *this*
    posting, so a bare 'hybrid' there needs no role attachment."""
    r = classify_remote(location="Calgary, AB - Hybrid", description="")
    assert r.is_hybrid is True


def test_lowercase_us_is_a_pronoun_not_a_country():
    r = classify_remote(
        location="Remote",
        remote_status="remote",
        description="Come build great things with us. Open to applicants across Canada.",
    )
    assert r.scope == "canada"
    assert r.qualifies is True


def test_canada_beats_us_when_both_named():
    r = classify_remote(
        location="Remote - Canada or US",
        description="Work from anywhere in Canada or the United States.",
    )
    assert r.scope == "canada"
    assert r.qualifies is True


def test_explicit_full_remote_outranks_incidental_hybrid():
    r = classify_remote(
        location="Remote",
        description="This is a 100% remote position. Our hybrid team spans three offices.",
    )
    assert r.is_hybrid is False
    assert r.qualifies is True


def test_unknown_scope_still_qualifies():
    """Excluding unknown-scope postings would cost more real jobs than the US
    noise it removes; the scoring penalty handles those instead."""
    r = classify_remote(location="Remote", description="A great opportunity.")
    assert r.scope == "unknown"
    assert r.qualifies is True


def test_evidence_offsets_point_at_the_matched_text():
    """The UI slices the input with these offsets, so they have to land on the
    phrase the classifier actually matched."""
    location = "Remote - Canada"
    description = "This is a hybrid role based downtown."
    r = classify_remote(location=location, description=description)

    assert r.evidence, "a verdict with no evidence cannot be interrogated"
    for ev in r.evidence:
        source = location if ev.where == "header" else description
        assert source[ev.start : ev.end] == ev.match


def test_every_result_reports_three_gates():
    for s in SAMPLES:
        r = classify_remote(s["location"], s["remote_status"], s["description"])
        assert [g.id for g in r.gates] == ["claims", "hybrid", "scope"]


def test_gate_details_are_human_readable_not_regex():
    """Gate copy is rendered on the site, so it must not leak raw patterns."""
    s = _sample("genuinely-hybrid")
    r = classify_remote(s["location"], s["remote_status"], s["description"])
    hybrid_gate = next(g for g in r.gates if g.id == "hybrid")
    assert "\\b" not in hybrid_gate.detail
    assert "(?:" not in hybrid_gate.detail
    assert "hybrid role" in hybrid_gate.detail


def test_empty_input_claims_nothing():
    r = classify_remote()
    assert r.claims_remote is False
    assert r.qualifies is False
    assert r.verdict == "not-remote"
