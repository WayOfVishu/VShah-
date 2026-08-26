"""
Scaffolded test for netdiag.dns_probe — skipped until #NET-2 lands
(see docs/TODO.md).
"""

import pytest

from netdiag import dns_probe


@pytest.mark.skip(reason="netdiag.dns_probe.measure_dns is not implemented yet — see docs/TODO.md #NET-2")
def test_resolves_a_known_good_hostname():
    # TODO once #NET-2 lands: this hits real DNS (there's no good way to
    # fake DNS resolution without mocking socket.getaddrinfo, and mocking
    # the one thing this function does defeats the point of the test) —
    # so pick a hostname stable enough to depend on in CI and assert
    # `resolved` is True and `duration_ms` is a small positive number.
    result = dns_probe.measure_dns("example.com")
    assert result["resolved"] is True
    assert result["duration_ms"] > 0


@pytest.mark.skip(reason="netdiag.dns_probe.measure_dns is not implemented yet — see docs/TODO.md #NET-2")
def test_reports_failure_for_a_hostname_that_cannot_resolve():
    # TODO: use a hostname guaranteed not to resolve (e.g. something under
    # the .invalid TLD, reserved by RFC 2606 specifically for this) and
    # assert your function's chosen failure shape (design question 3 in
    # dns_probe.py) rather than letting socket.gaierror escape the test.
    result = dns_probe.measure_dns("this-should-not-resolve.invalid")
    assert result["resolved"] is False
