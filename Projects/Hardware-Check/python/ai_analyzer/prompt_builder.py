"""
Turns merged telemetry into a prompt Gemini can actually give a useful,
structured answer to — project-charter.md Section 5.3.

TODO (Phase 5, week 9 — docs/TODO.md #AI-1). Secondary learning objective
(project-charter.md Section 2: "structured prompting"). The functional
requirement to build against (Section 5.3): "Build a structured prompt
(define the schema you want back — don't let the model free-form it)."

This is really two related design tasks, not one:
  (a) the prompt text itself — what telemetry actually matters for a
      Gemini call to reason about usefully, and how you phrase the ask
      (e.g. "you are a systems diagnostics assistant..." framing, whether
      you include the raw JSON verbatim or summarize it first)
  (b) the *response schema* — the shape you're demanding back: summary,
      likely cause(s), suggested fix(es), rough severity (Section 5.3).
      The google-genai SDK supports a `response_schema` parameter on
      generate_content that constrains the model's output to match a
      schema you provide (a Pydantic model or a JSON-schema dict) — that's
      the "don't let the model free-form it" mechanism the requirement is
      pointing at. Look up "google-genai structured output response_schema"
      in the SDK docs before designing this; don't hand-roll prompt-based
      JSON coaxing when the SDK gives you an enforced option.

Design questions:
  1. Do you send the FULL merged telemetry dict, or trim/summarize it
     first? Bigger prompt -> more tokens -> matters even on a free tier
     with a request-count limit, not just a paid per-token one
     (project-charter.md Section 9).
  2. What does "rough severity" mean as a schema field — a free-text
     string, or a constrained enum (low/medium/high)? An enum is easier for
     response_parser.py and report_writer.py to handle downstream; a free
     string is easier for the model to reason with. Which do you pick, and
     does the schema mechanism from (b) above let you enforce it either way?
  3. If a network probe failed and its section of the telemetry is missing
     (see engine_runner.py / ping_probe.py's reliability design questions),
     should the prompt say anything about that explicitly, or just omit
     the field and let Gemini not comment on it?
"""

from typing import Any


def build_prompt(telemetry: dict[str, Any]) -> str:
    """Build the prompt text sent to Gemini, from the merged telemetry dict."""
    raise NotImplementedError("build_prompt() is not implemented yet — see docs/TODO.md #AI-1")


# TODO: define the response schema here too (a Pydantic BaseModel is the
# most common way to hand this to google-genai's response_schema param —
# see this module's docstring, point (b)). Naming it something like
# `AnalysisSchema` and importing it from ai_analyzer.gemini_client and
# ai_analyzer.response_parser keeps one single source of truth for the
# shape both those modules depend on.
