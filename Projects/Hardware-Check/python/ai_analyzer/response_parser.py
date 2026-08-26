"""
Turns Gemini's raw response into the structured dict the rest of the app
uses — project-charter.md Section 5.3: "Parse the response into: summary,
likely cause(s), suggested fix(es), rough severity."

TODO (Phase 5, week 9 — docs/TODO.md #AI-3).

If you used the SDK's response_schema mechanism (prompt_builder.py's TODO),
most of "parsing" may already be done for you by the SDK — but "the model
returned something that doesn't match the schema" is still a real failure
mode worth handling explicitly, not assuming away.

Design questions:
  1. What does a genuinely malformed response look like in practice (empty
     response, a schema-shaped object with an empty causes/fixes list,
     the SDK falling back to plain text because the model couldn't satisfy
     the schema)? Which of those should raise, and which should return a
     "best effort" partial result?
  2. report_writer.py (already built) expects `analysis` to be a dict with
     at least `summary`, `severity`, and optionally `causes`/`fixes` list
     keys, or None. Keep this function's output shape consistent with that
     contract, or update report_writer.py's expectations to match yours —
     don't let the two silently drift apart.
"""

from typing import Any


def parse_analysis(raw_response: Any) -> dict[str, Any]:
    """Convert the SDK's raw response object/text into the app's analysis dict.

    Expected shape once implemented, e.g.:
        {"summary": "...", "causes": ["..."], "fixes": ["..."], "severity": "low"}
    """
    raise NotImplementedError("parse_analysis() is not implemented yet — see docs/TODO.md #AI-3")
