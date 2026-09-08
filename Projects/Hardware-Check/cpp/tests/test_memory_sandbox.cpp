// Scaffolded tests for MemorySandbox — every body is empty until #MEM-1 and
// #MEM-T1 land (see docs/TODO.md). Same split as everywhere else in this
// project: the harness, the fixture shape and the *questions* are built; the
// assertions are yours.
//
// Read include/sysdiag/memory_sandbox.hpp's design questions first. This file
// adds one more, and it is the hardest one in the project:
//
//   How do you write a *passing* test that proves a demo is BROKEN?
//
// That is not rhetorical. project-charter.md Section 13 requires the three
// buggy demos be "demonstrably *not* clean" before the Phase 2 refactor — "a
// clean run before the refactor would mean the demo wasn't actually exercising
// the bug". So a green test suite has to somehow assert that memory was leaked,
// that a freed pointer was used, and that a double free happened. A test that
// just calls demo_leak() and checks it returned a struct proves nothing: it
// would pass identically against a demo_leak() that forgot to leak.
//
// Three sub-questions worth sitting with before you write a line:
//
//   1. ASan aborts the process on the first error it detects, by default. Two
//      of these four demos are undefined behavior. So what happens to your test
//      binary when it runs them — and what does that do to every test scheduled
//      to run after them? (This is memory_sandbox.hpp's design question #2
//      arriving from the other side: there it was about protecting
//      sysdiag_engine's normal path; here it is about the test runner's own
//      process.)
//
//   2. Given #1 — does asserting on undefined behavior belong in the same
//      process as the assertion at all? Look up gtest's *death tests*
//      (EXPECT_DEATH / EXPECT_EXIT) before deciding. They run the statement in
//      a forked child and assert on how that child died, which is a very
//      different tool from EXPECT_EQ and exists for exactly this situation.
//      Note the tradeoff: death tests are slow and interact badly with threads,
//      so they are not a free win — decide whether the cost is worth it here,
//      and write down why. That reasoning belongs in the Phase 2 README
//      comparison.
//
//   3. There are two genuinely different things you could assert on, and they
//      are not equally good:
//        (a) the SandboxBugReport the demo returned — cheap, in-process, but it
//            only proves your own bookkeeping agrees with itself. A demo that
//            sets ran_to_completion=false without ever allocating would pass.
//        (b) what the *sanitizer* said — expensive, out-of-process, but it is
//            external evidence: ASan's "detected memory leaks" or
//            "heap-use-after-free" is a second opinion your code cannot fake.
//      (a) is a unit test. (b) is the acceptance criterion. Decide which of
//      these tests wants which, and be honest that some may want both.
//
// Build and run (from the repo root, inside WSL2):
//   cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON
//   cmake --build cpp/build
//   ctest --test-dir cpp/build --output-on-failure
//
// With ASan on — expect this to behave differently, and expect that difference
// to be informative rather than annoying:
//   cmake -S cpp -B cpp/build -DBUILD_TESTING=ON -DENABLE_ASAN=ON
//   cmake --build cpp/build && ctest --test-dir cpp/build --output-on-failure

#include "sysdiag/memory_sandbox.hpp"

#include <gtest/gtest.h>

namespace {

// --- The control case -------------------------------------------------------
// Start here. It is the only one of the four unambiguously safe to run
// in-process, which makes it the right place to work out what a
// SandboxBugReport should even contain before the harder three force the
// question.

TEST(MemorySandbox, CleanCycleCompletesAndReportsClean) {
    // TODO (#MEM-T1): allocate/use/free with no bug, and assert the report says
    // so. Decide what "says so" means — bug_name? ran_to_completion? both? The
    // struct has three fields and you chose their semantics in #MEM-1; this is
    // where you find out whether those semantics were actually usable.
}

TEST(MemorySandbox, CleanCycleIsCleanUnderTheSanitizer) {
    // TODO (#MEM-T1): the (b)-flavoured twin of the test above, and the one
    // that matters for Section 13. If demo_clean_cycle() is genuinely clean,
    // running it under ASan produces no diagnostic and exits 0.
    //
    // Design question: can you assert that from *inside* a test binary that is
    // itself running under ASan? Or does proving "the sanitizer stayed quiet"
    // require running the demo somewhere you control the exit code — a death
    // test, a subprocess, or a separate ctest entry that runs the real
    // sysdiag_engine binary with --memory-demo and checks its status? All three
    // are defensible. Pick one and leave a comment saying why.
}

// --- The leak ---------------------------------------------------------------
// Not undefined behavior — a leak is well-defined, it is just wrong. That makes
// this the gentlest of the three buggy demos and the right one to attempt
// second.

TEST(MemorySandbox, LeakIsActuallyLeaked) {
    // TODO (#MEM-T1): prove memory was leaked.
    //
    // The trap: leaked memory has no observable effect inside the process that
    // leaked it. There is no portable C++ call that answers "am I currently
    // leaking?" — that is the entire reason LeakSanitizer exists as a separate
    // tool. So an in-process EXPECT_* almost certainly cannot do this honestly.
    //
    // Look at __lsan_do_recoverable_leak_check() (<sanitizer/lsan_interface.h>)
    // before reaching for a subprocess. It is guarded behind __has_feature or
    // __SANITIZE_ADDRESS__, so anything you write here still has to compile in
    // a non-ASan build — a small portability exercise worth doing properly
    // rather than with a bare #ifdef and a shrug.
}

// --- The two undefined-behavior demos ---------------------------------------
// Read design question #2 above before writing either of these. If you find
// yourself writing a plain EXPECT_EQ against demo_double_free(), stop — that is
// the test that will pass locally, pass in CI, and mean nothing.

TEST(MemorySandbox, DanglingPointerUseIsDetected) {
    // TODO (#MEM-T1): heap-use-after-free is what ASan is *best* at catching,
    // and it reports it loudly. So the question is not "will it be detected" —
    // it is "how does my test observe the detection without dying alongside
    // it?"
    //
    // Second, subtler question: without ASan this demo may well appear to work
    // fine — the freed memory is often still mapped and still holds the old
    // value. Should this test FAIL in a non-sanitized build (because it cannot
    // prove what it claims), SKIP with GTEST_SKIP() and a reason, or pass
    // vacuously? Only one of those three is honest. Argue for your choice in a
    // comment; this is exactly the kind of judgment the README writeup wants.
}

TEST(MemorySandbox, DoubleFreeIsDetected) {
    // TODO (#MEM-T1): same shape as the dangling-pointer test, different
    // failure mode — glibc itself often catches this one and aborts with
    // "free(): double free detected in tcache 2" even with no sanitizer at all.
    //
    // So this demo can die in at least three distinct ways depending on build:
    // ASan diagnostic, glibc abort, or (unluckily) silent corruption. If you
    // use a death test, its matcher decides which of those you accept — a
    // matcher tight enough to only accept ASan's wording will fail the plain
    // Debug build, and one loose enough to accept anything will pass on a crash
    // that had nothing to do with your demo. Choose deliberately.
}

// --- The aggregate ----------------------------------------------------------

TEST(MemorySandbox, RunAllReportsEveryDemo) {
    // TODO (#MEM-T1): assert run_all() returns one report per demo. This is the
    // cheapest test in the file and the only one you can write before deciding
    // anything above — but it inherits memory_sandbox.hpp's design question #2
    // wholesale: if run_all() actually runs the UB demos, this test cannot
    // survive its own subject. If you gated run_all() behind an opt-in flag,
    // this is where that decision gets exercised for the first time.
}

}  // namespace
