"""
DNS resolution timing — project-charter.md Section 5.2.

TODO (Phase 3, weeks 6-7 — docs/TODO.md #NET-2). Primary learning objective
(project-charter.md Section 2: "DNS resolution ... by implementing them").

Unlike ping_probe.py, this one doesn't need a subprocess — Python's
standard library resolves hostnames directly. The interesting part isn't
the resolution call itself (that's one line), it's timing it correctly and
deciding what "the result" even means when a hostname resolves to more
than one address.

Design questions:
  1. socket.getaddrinfo() vs. socket.gethostbyname() — they don't return the
     same shape of data (one supports IPv6 and returns multiple result
     tuples, the other is IPv4-only and simpler). Which fits "DNS
     resolution timing" better, and why might you want every address a
     hostname resolves to rather than just the first one?
  2. What are you actually timing — the wall-clock cost of one resolution
     call (time.perf_counter() before/after), or something about caching
     behavior (does calling it twice in a row for the same host give a
     suspiciously fast second result — and if so, whose cache is that,
     yours or the OS's)? project-charter.md doesn't require you to detect
     caching, but it's worth understanding while you're in here.
  3. A hostname that doesn't resolve raises socket.gaierror, not a return
     value — same reliability question as ping_probe.py's design question
     2: catch it here and return a structured failure, or let it propagate?
     Be consistent with whatever you decided over there.
"""

from typing import Any


def measure_dns(hostname: str) -> dict[str, Any]:
    """Resolve `hostname` and report how long it took and what it resolved to.

    Expected shape once implemented, e.g.:
        {"hostname": hostname, "resolved": True, "duration_ms": 4.2, "addresses": ["1.2.3.4"]}
    """
    raise NotImplementedError("measure_dns() is not implemented yet — see docs/TODO.md #NET-2")
