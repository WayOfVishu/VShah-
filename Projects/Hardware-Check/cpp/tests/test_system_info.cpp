// Scaffolded tests for collect_system_snapshot() — empty until #SYS-1 and
// #MEM-T1 land (see docs/TODO.md). Harness and questions built, assertions
// yours.
//
// This file has the opposite problem to test_memory_sandbox.cpp. There, the
// difficulty was that the subject misbehaves on purpose. Here the subject
// behaves fine — but it reads the *live machine*, so you cannot know the right
// answer in advance. cpu_load_percent is different every run. mem_available_kb
// changes between two consecutive reads. top_processes depends on what happens
// to be running.
//
// So the question this file is really about:
//
//   What do you assert when you cannot know the expected value?
//
// The answer is invariants, not values — properties that must hold for *any*
// correct snapshot on any machine. Some are obvious once stated
// (mem_available_kb <= mem_total_kb). Some are worth thinking about: is
// cpu_core_count > 0 a safe assertion? Is disk_total_kb > 0? What about
// top_processes being non-empty — is there any legitimate machine where a
// correct implementation returns zero processes?
//
// Be careful about the weak ones. `EXPECT_GE(snap.mem_total_kb, 0)` is
// vacuously true for an unsigned type and will pass against a function that
// returns a default-constructed struct without reading anything at all. That is
// the failure mode to design against here: SystemSnapshot's fields are all
// zero-initialised (see system_info.hpp), so a stub that does nothing produces
// a *plausible-looking* struct. Your tests must be able to tell "read the
// machine and found 0" apart from "never read the machine".
//
// The second, larger question — worth deciding before you write #SYS-1 rather
// than after:
//
//   Should parsing be separable from reading?
//
// Right now system_info.hpp declares exactly one function, and it both opens
// /proc and interprets what it finds. That is untestable by construction: you
// cannot hand it a known /proc/meminfo and check the parse, because it always
// reads the real one. If instead the parsing lived in a small function taking a
// string or an istream, you could feed it a fixture captured from a real
// machine and assert exact values — the one place in this file where exact
// values are possible.
//
// That refactor is not scaffolded, and system_info.hpp is not written to
// require it. Doing it means changing a header that was handed to you, which is
// allowed and occasionally correct. If you do it, say so in the README; if you
// decide against it, say why. Either is a defensible engineering answer. Not
// noticing the question is the only bad outcome.

#include "sysdiag/system_info.hpp"

#include <gtest/gtest.h>

namespace {

// --- Invariants on a live snapshot ------------------------------------------

TEST(SystemInfo, SnapshotIsInternallyConsistent) {
    // TODO (#MEM-T1): call collect_system_snapshot() once and assert the
    // relationships between fields that must hold regardless of machine —
    // available <= total for both memory and disk, and whatever else you can
    // justify. Each assertion should be one you could defend if asked "why must
    // that be true?"
}

TEST(SystemInfo, SnapshotActuallyReadTheMachine) {
    // TODO (#MEM-T1): the anti-vacuity test, and the important one in this
    // file. Assert something that CANNOT be true of a default-constructed
    // SystemSnapshot — cpu_model non-empty, cpu_core_count >= 1, mem_total_kb
    // strictly positive.
    //
    // Then check your work by asking: if I deleted the body of
    // collect_system_snapshot() and left `return SystemSnapshot{};`, would this
    // test fail? If not, it is not testing anything.
}

TEST(SystemInfo, TopProcessesAreWellFormed) {
    // TODO (#MEM-T1): system_info.hpp leaves "however many you decide is a
    // reasonable top N" to you, so there is no fixed count to assert. Assert
    // the shape instead: every entry has a positive pid, a non-empty name, and
    // — if you named the field honestly — the list is actually sorted by
    // resident_kb descending.
    //
    // That last one is worth checking rather than assuming. "top_processes"
    // claims an ordering in its name; a test is where that claim either holds
    // or quietly turns out to be false.
}

// --- Stability --------------------------------------------------------------

TEST(SystemInfo, TwoConsecutiveSnapshotsAgreeOnWhatCannotChange) {
    // TODO (#MEM-T1): take two snapshots back to back. Some fields must be
    // identical across them (cpu_model, cpu_core_count, mem_total_kb — the
    // hardware did not change in 3 milliseconds). Others are expected to
    // differ, and asserting they are equal would make this test flaky on a busy
    // machine.
    //
    // Sorting the fields into those two buckets is the actual exercise. If a
    // field is in neither — you cannot say whether it should be stable — that
    // usually means its semantics are still undecided. system_info.hpp flags
    // exactly one of these already: cpu_load_percent is "instantaneous or
    // short-window average — your call, document which". This test is where
    // that call stops being theoretical.
}

}  // namespace
