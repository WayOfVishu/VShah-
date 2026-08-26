"""
Writes a finished report (telemetry + Gemini analysis) to disk.

Plumbing, not a learning exercise — this is generic "serialize a dict to a
timestamped file" logic with no project-specific concept in it.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from netdiag import config


def write_report(telemetry: dict[str, Any], analysis: dict[str, Any] | None, fmt: str = "json") -> Path:
    """Write the combined telemetry + analysis to data/reports/, timestamped.

    fmt: "json" (machine-readable, the full payload) or "text" (a short
    human-readable summary — just the Gemini analysis fields, not the raw
    telemetry dump).

    Returns the path written to, so the CLI can tell the user where to find it.
    """
    config.ensure_data_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {"telemetry": telemetry, "analysis": analysis}

    if fmt == "json":
        out_path = config.REPORTS_DIR / f"report_{timestamp}.json"
        out_path.write_text(json.dumps(payload, indent=2))
        return out_path

    if fmt == "text":
        out_path = config.REPORTS_DIR / f"report_{timestamp}.txt"
        lines = [f"Diagnostic report — {timestamp}", ""]
        if analysis:
            lines.append(f"Summary: {analysis.get('summary', '(none)')}")
            lines.append(f"Severity: {analysis.get('severity', '(none)')}")
            causes = analysis.get("causes", [])
            fixes = analysis.get("fixes", [])
            if causes:
                lines.append("\nLikely cause(s):")
                lines.extend(f"  - {c}" for c in causes)
            if fixes:
                lines.append("\nSuggested fix(es):")
                lines.extend(f"  - {f}" for f in fixes)
        else:
            lines.append("(no Gemini analysis attached to this report)")
        out_path.write_text("\n".join(lines))
        return out_path

    raise ValueError(f"unknown report format: {fmt!r} (expected 'json' or 'text')")
