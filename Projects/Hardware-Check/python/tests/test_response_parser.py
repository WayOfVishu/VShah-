"""
Scaffolded test for ai_analyzer.response_parser — skipped until #AI-3 lands
(see docs/TODO.md).

This is the module where the project meets a fact it cannot control: the model
may return something you did not ask for. Everything upstream is deterministic —
your telemetry, your prompt, your schema. The response is the one input to this
system produced by something that can be wrong in novel ways.

So the tests worth writing here are almost entirely the malformed cases. The
happy path is one test; design question 1 lists four distinct failure modes and
each deserves its own, because each has a different *right answer*:

    empty response                  -> almost certainly raise
    schema-shaped, empty causes[]   -> probably valid! a clean machine has no causes
    schema-shaped, missing summary  -> ?
    plain text, schema not honoured -> ?

That second one is the trap. It is easy to write a parser that treats "no
causes" as malformed, and it is wrong — a healthy machine legitimately produces
an analysis with nothing to fix. If your parser raises on it, the tool breaks
precisely when everything is fine.

The contract to hold onto (design question 2): report_writer.py is already
built and already expects `summary`, `severity`, and optional `causes`/`fixes`
lists, or None. These tests are where you keep the two sides honest.
"""

import pytest

from ai_analyzer import response_parser


@pytest.fixture
def well_formed_response():
    """What the SDK hands back when the model honoured the schema. Shaped to
    match response_parser.py's docstring example — if you changed that shape
    when writing #AI-1's AnalysisSchema, change it here too and make sure
    report_writer.py agrees."""
    return {
        "summary": "Memory pressure with degraded network reachability.",
        "causes": ["hungry_process (pid 1234) holding ~9GB resident"],
        "fixes": ["Restart or investigate pid 1234", "Check the upstream link"],
        "severity": "high",
    }


@pytest.mark.skip(reason="ai_analyzer.response_parser.parse_analysis is not implemented yet — see docs/TODO.md #AI-3")
def test_parses_a_well_formed_response(well_formed_response):
    # TODO once #AI-3 lands: the happy path. Assert the returned dict carries
    # all four keys with the right types — causes and fixes as lists, not as a
    # single joined string.
    #
    # Worth asserting the types explicitly even though it feels pedantic: if the
    # SDK hands back a Pydantic object rather than a dict, "it has a summary"
    # can be true while `result["summary"]` still raises. The type assertion is
    # what catches that.
    pytest.fail("write me")


@pytest.mark.skip(reason="ai_analyzer.response_parser.parse_analysis is not implemented yet — see docs/TODO.md #AI-3")
def test_empty_causes_and_fixes_is_valid_not_malformed(well_formed_response):
    # TODO: the trap described in the module docstring above. A healthy machine
    # produces a real analysis with an empty causes list and an empty fixes
    # list. Assert this parses successfully and does NOT raise.
    #
    # Then check report_writer.py actually renders that case sensibly rather
    # than printing an empty bulleted list under a "Likely causes" heading. The
    # parser being right is only half of it.
    well_formed_response["causes"] = []
    well_formed_response["fixes"] = []
    pytest.fail("write me")


@pytest.mark.skip(reason="ai_analyzer.response_parser.parse_analysis is not implemented yet — see docs/TODO.md #AI-3")
def test_empty_response_raises():
    # TODO: empty string, None, or an object with no content. This is the one
    # failure mode where raising is almost certainly right — there is no partial
    # result to salvage, and returning {"summary": "", ...} would put an empty
    # section in the report as though the model had genuinely said nothing was
    # wrong.
    #
    # Assert on your own exception type if you defined one. Letting a bare
    # KeyError or AttributeError escape from here means the CLI's error message
    # will be about dictionary access rather than about Gemini.
    pytest.fail("write me")


@pytest.mark.skip(reason="ai_analyzer.response_parser.parse_analysis is not implemented yet — see docs/TODO.md #AI-3")
def test_missing_required_field_is_handled_deliberately():
    # TODO: a response with causes and fixes but no summary. Design question 1
    # asks which failures raise and which return a best-effort partial — this is
    # the case that forces you to answer it.
    #
    # Either answer is defensible. What is not defensible is the third option
    # that happens by default: a KeyError from deep inside the parser that the
    # CLI surfaces as a stack trace. Write the test for the behaviour you chose,
    # so the choice is recorded somewhere other than your memory.
    pytest.fail("write me")


@pytest.mark.skip(reason="ai_analyzer.response_parser.parse_analysis is not implemented yet — see docs/TODO.md #AI-3")
def test_plain_text_fallback_when_schema_was_not_honoured():
    # TODO: the model ignored the schema and returned prose. If you used the
    # SDK's response_schema this should be rare — but "rare" is not "impossible",
    # and this is the failure that will happen once, in front of someone, six
    # months from now.
    #
    # Decide: salvage it into {"summary": <the prose>, "severity": "unknown"},
    # or reject it? If you salvage, note that "unknown" has to be a severity
    # report_writer.py can handle — which loops back to #AI-1 design question 2
    # and whether severity is an enum. If it is a closed enum, "unknown" has to
    # be a member of it, and that is a schema change, not a parser change.
    pytest.fail("write me")
