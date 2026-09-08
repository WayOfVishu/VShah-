"""
Scaffolded test for ai_analyzer.prompt_builder — skipped until #AI-1 lands
(see docs/TODO.md). Scaffolding built, assertions yours, same split as the
netdiag tests.

Testing a prompt builder is unlike testing a probe, and the difference is the
point of this file. There is no correct output string to compare against: two
reasonable prompts can be worded completely differently and both work. So
asserting `build_prompt(t) == "You are a systems diagnostics assistant..."`
would be a test that fails every time you improve the wording, which is the
definition of a brittle test.

What is worth asserting is that the prompt *carries the information it must
carry*, and that it survives the inputs that will actually occur:

  - the telemetry that matters made it into the string at all
  - a missing probe section (see design question 3 in the module docstring)
    does not produce a KeyError or the literal text "None"
  - whatever you decided about trimming (design question 1) actually happens

The schema half of #AI-1 is easier to test properly, and more valuable —
`AnalysisSchema` is a real object with a fixed shape, so it can be asserted on
exactly. That is what the second half of this file is for.
"""

import pytest

from ai_analyzer import prompt_builder


@pytest.fixture
def merged_telemetry():
    """A minimal merged-telemetry dict shaped like what engine_runner.run_engine()
    plus the netdiag probes produce. Deliberately small — a fixture the size of
    a real snapshot would make it hard to see which field an assertion is
    actually about."""
    return {
        "system": {
            "cpu_model": "Test CPU @ 3.00GHz",
            "cpu_core_count": 8,
            "cpu_load_percent": 91.4,
            "mem_total_kb": 16_000_000,
            "mem_available_kb": 400_000,
            "top_processes": [
                {"pid": 1234, "name": "hungry_process", "resident_kb": 9_000_000},
            ],
            "disk_total_kb": 500_000_000,
            "disk_available_kb": 2_000_000,
        },
        "memory_sandbox": [],
        "network": {
            "ping": {"host": "1.1.1.1", "avg_ms": 812.5, "packet_loss_percent": 40.0},
            "dns": {"host": "example.com", "resolved_ms": 1500.0},
        },
    }


@pytest.mark.skip(reason="ai_analyzer.prompt_builder.build_prompt is not implemented yet — see docs/TODO.md #AI-1")
def test_prompt_contains_the_signals_worth_reasoning_about(merged_telemetry):
    # TODO once #AI-1 lands: assert the prompt mentions the things a diagnostic
    # answer would have to be about. The fixture is deliberately a sick machine
    # — 91.4% CPU, 2.5% memory free, 40% packet loss, 1.5s DNS — so if any of
    # those numbers is absent from the prompt, Gemini cannot possibly comment on
    # it and the analysis will be vague for a reason that is your fault, not the
    # model's.
    #
    # Assert on substrings/values, not on phrasing. `"91.4" in prompt` survives
    # you rewriting the surrounding sentence; `"CPU load is 91.4%" in prompt`
    # does not.
    prompt = prompt_builder.build_prompt(merged_telemetry)
    assert isinstance(prompt, str) and prompt


@pytest.mark.skip(reason="ai_analyzer.prompt_builder.build_prompt is not implemented yet — see docs/TODO.md #AI-1")
def test_missing_probe_section_does_not_break_the_prompt(merged_telemetry):
    # TODO: this is design question 3 from the module docstring, as a test. Drop
    # the "network" key entirely (a run where every probe failed) and assert
    # build_prompt still returns a usable string.
    #
    # Then decide the harder half deliberately rather than by accident: should
    # the prompt SAY the network probes failed, or silently omit them? Those
    # produce different analyses — a model told "DNS timed out" may diagnose the
    # outage; a model shown nothing about DNS will assume it was fine. Write the
    # assertion for whichever you chose, and a comment for why.
    del merged_telemetry["network"]
    prompt = prompt_builder.build_prompt(merged_telemetry)
    assert isinstance(prompt, str) and prompt


@pytest.mark.skip(reason="The AnalysisSchema response schema is not defined yet — see docs/TODO.md #AI-1 point (b)")
def test_analysis_schema_matches_what_report_writer_expects():
    # TODO: once AnalysisSchema exists (module docstring point (b)), assert its
    # fields line up with the contract response_parser.py's design question 2
    # describes — summary, severity, and the causes/fixes lists that
    # report_writer.py already reads.
    #
    # This test exists because that contract is currently held together by three
    # docstrings agreeing with each other by hand. The moment it is a schema
    # object, it can be checked instead of trusted — and this is the cheapest
    # place in the project to catch the two sides drifting apart.
    #
    # If you made severity an enum (design question 2), assert the allowed values
    # here too. That is the assertion that will one day catch a model returning
    # "critical" when report_writer only knows low/medium/high.
    pytest.fail("write me")
