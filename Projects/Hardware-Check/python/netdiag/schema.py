"""
Shared JSON schema conventions between the C++ engine and the Python side.

Plumbing, not a learning exercise — this file just names the top-level keys
both languages agree on, and merges the two halves into one payload before
it goes to the Gemini analyzer. The C++ side's contract lives in
cpp/include/sysdiag/telemetry_json.hpp; if you add a field on either side,
update the matching comment on the other.
"""

from typing import Any

# Top-level keys sysdiag_engine's JSON output uses (must match
# cpp/src/telemetry_json.cpp's build_report()).
SYSTEM_KEY = "system"
MEMORY_SANDBOX_KEY = "memory_sandbox"

# Top-level keys the Python probes add (netdiag/ping_probe.py,
# dns_probe.py, port_scan.py all return dicts under these keys once built).
PING_KEY = "ping"
DNS_KEY = "dns"
PORT_SCAN_KEY = "port_scan"


def merge_telemetry(
    engine_report: dict[str, Any],
    ping_result: dict[str, Any] | None,
    dns_result: dict[str, Any] | None,
    port_scan_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Combine the C++ engine's report with the Python network probes' output
    into the single payload ai_analyzer.gemini_client sends to the API.

    Any probe result that's None (a probe wasn't run, or failed and was
    caught upstream — see engine_runner.py's #NET-4 TODO) is simply omitted
    rather than included as null, so the prompt builder isn't asking Gemini
    to reason about data that was never collected.
    """
    merged: dict[str, Any] = dict(engine_report)  # shallow copy; don't mutate the caller's dict
    if ping_result is not None:
        merged[PING_KEY] = ping_result
    if dns_result is not None:
        merged[DNS_KEY] = dns_result
    if port_scan_result is not None:
        merged[PORT_SCAN_KEY] = port_scan_result
    return merged
