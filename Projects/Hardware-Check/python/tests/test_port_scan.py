"""
Scaffolded test for netdiag.port_scan — skipped until #NET-3 lands
(see docs/TODO.md). The scaffolding (imports, fixture shape, what to assert
against) is built; the assertions themselves are yours, same split as the
production code.
"""

import socket
import threading

import pytest

from netdiag import port_scan


@pytest.fixture
def listening_port():
    """Spin up a throwaway TCP listener on an OS-assigned port so the test
    doesn't depend on any real external host or a hardcoded port number
    that might already be in use."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    thread = threading.Thread(target=server.accept, daemon=True)
    thread.start()
    yield port
    server.close()


@pytest.mark.skip(reason="netdiag.port_scan.scan_ports is not implemented yet — see docs/TODO.md #NET-3")
def test_scan_finds_the_open_port(listening_port):
    # TODO once #NET-3 lands: scan a small range containing `listening_port`
    # plus at least one port you know is closed, and assert the result's
    # open_ports list contains exactly the one you opened above — not more,
    # not fewer. A test that only checks "the open port is in there
    # somewhere" wouldn't catch a scanner that (incorrectly) reports every
    # port as open.
    result = port_scan.scan_ports("127.0.0.1", (listening_port, listening_port + 1))
    assert listening_port in result["open_ports"]
