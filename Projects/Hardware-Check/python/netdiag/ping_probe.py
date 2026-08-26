"""
ICMP latency check (avg/min/max) — project-charter.md Section 5.2.

TODO (Phase 3, weeks 6-7 — docs/TODO.md #NET-1). One of this project's
Primary learning objectives (project-charter.md Section 2: "networking
fundamentals ... by implementing them, not just describing them").

Design decision already made for you, so you don't rediscover it the hard
way: this shells out to the system `ping` command via subprocess rather
than opening a raw ICMP socket directly. A raw socket needs elevated
privileges on most default Linux configs (root, or CAP_NET_RAW, or a
sysctl tweak to net.ipv4.ping_group_range) — project-charter.md Section 3
explicitly scopes out anything requiring elevated privileges, and the
system `ping` binary is already set up with the one process that needs
that privilege, so you get the ICMP round trip without needing it yourself.

What you're actually building: run `ping -c <count> <host>` (WSL2/Linux
ping syntax — note this is NOT the same flag set as Windows' ping.exe, in
case you ever test outside WSL2), capture stdout, and turn it into
avg/min/max latency numbers.

Design questions:
  1. Two ways to get avg/min/max: parse ping's own summary line at the end
     (`rtt min/avg/max/mdev = ...`), or parse each individual `time=X ms`
     line and compute the three yourself. The second is more code but
     means you're not depending on ping's summary line format (which does
     vary slightly by ping version) staying stable. Pick one and note why.
  2. What does a timeout or "Destination Host Unreachable" line look like
     in ping's output, and what should this function return in that case —
     raise, or return a result dict with an explicit `reachable: False`
     field? (project-charter.md Section 6: one bad reading shouldn't crash
     the whole diagnostic run — think about which choice makes that easier
     for engine_runner.py's caller.)
  3. subprocess.run has a `timeout=` parameter — what happens if ping
     itself hangs longer than you expect? What should this function do
     about it?

Reference: Python subprocess docs; `man ping` (inside WSL2).
"""

from typing import Any


def measure_ping(host: str, count: int = 4) -> dict[str, Any]:
    """Run `count` ICMP echoes against `host`, return avg/min/max latency (ms).

    Expected shape once implemented, e.g.:
        {"host": host, "reachable": True, "avg_ms": 12.3, "min_ms": 10.1, "max_ms": 15.8}
    (or a `reachable: False` variant per design question 2 above — the exact
    shape of the failure case is yours to decide, just be consistent.)
    """
    raise NotImplementedError("measure_ping() is not implemented yet — see docs/TODO.md #NET-1")
