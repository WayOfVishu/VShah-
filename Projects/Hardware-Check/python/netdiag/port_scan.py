"""
Basic TCP port scan over a configurable range — project-charter.md
Section 5.2.

TODO (Phase 3, weeks 6-7 — docs/TODO.md #NET-3). Primary learning objective
(project-charter.md Section 2: "sockets ... by implementing them"). This is
the module that most directly exercises actual socket programming — Beej's
Guide (project-charter.md Section 11) is the right reference to have open.

Constraint already locked in (project-charter.md Section 3): TCP connect
scanning only, no raw sockets, no elevated privileges. That means you're
using socket.socket(socket.AF_INET, socket.SOCK_STREAM) and either
connect() or connect_ex(), not anything lower-level.

Design questions:
  1. connect() raises on failure (needs a try/except per port); connect_ex()
     returns an errno integer instead (0 = success). Which reads cleaner
     for "try N ports in a row and keep going regardless of individual
     failures"?
  2. Every closed/filtered port needs its own connection attempt to time
     out or get refused before you move to the next one. For a 100-port
     range with a 1-second timeout each, what's the worst-case wall-clock
     time if you scan strictly sequentially? Is that acceptable for this
     project, or does it push you toward running scans concurrently
     (concurrent.futures.ThreadPoolExecutor is the standard-library tool
     for that)? Get a correct sequential version working FIRST — don't
     reach for threads until you've confirmed the single-threaded logic is
     right; debugging socket logic and thread logic at the same time is a
     bad time.
  3. socket.settimeout() — what timeout value balances "don't wait forever
     on a filtered port" against "don't report a slow-but-open port as
     closed"? There's no single right answer; pick one and say why in a
     comment.
  4. project-charter.md's own risk table doesn't mention this, but think
     about it anyway: should port_scan default to scanning localhost, or
     does scanning arbitrary hosts the caller supplies raise any concerns
     worth a comment in this file (rate limits, being mistaken for
     reconnaissance against a host that isn't yours)?
"""

from typing import Any


def scan_ports(host: str, port_range: tuple[int, int]) -> dict[str, Any]:
    """Attempt a TCP connection to every port in `port_range` (inclusive start,
    exclusive end, i.e. range(port_range[0], port_range[1])) against `host`.

    Expected shape once implemented, e.g.:
        {"host": host, "open_ports": [1025, 1080], "scanned_count": 100}
    """
    raise NotImplementedError("scan_ports() is not implemented yet — see docs/TODO.md #NET-3")
