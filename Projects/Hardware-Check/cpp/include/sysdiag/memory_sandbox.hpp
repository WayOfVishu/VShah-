#pragma once

#include <string>
#include <vector>

namespace sysdiag {

// One demo run's result. This is what src/memory_sandbox.cpp's methods
// return and what telemetry_json.cpp serializes into the report.
struct SandboxBugReport {
    std::string bug_name;    // e.g. "leak", "dangling_pointer", "double_free", "clean_cycle"
    bool ran_to_completion;  // did the demo run without the process dying? (matters for the crash-y ones)
    std::string notes;       // free-form — what you actually observed running this under ASan/Valgrind
};

// ============================================================================
// TODO (Phase 1, weeks 3-4 — docs/TODO.md #MEM-1). THE core learning module
// of this entire project (project-charter.md Section 2, Primary objective
// #1). Implemented in src/memory_sandbox.cpp using raw `new`/`delete` —
// deliberately, not as an oversight. Do not reach for std::unique_ptr or
// std::shared_ptr in this pass; that refactor is Phase 2 (week 5), and the
// whole point of doing it as a second, separate pass is having a genuine
// "before" to compare against (Acceptance Criteria in project-charter.md
// Section 13 asks for exactly that comparison in the README).
//
// Four demos, matching project-charter.md Section 5.1's spec almost
// word for word:
//   - demo_clean_cycle        — allocate, use, free. Your control case.
//   - demo_leak               — allocate, "forget" to free.
//   - demo_dangling_pointer   — free, then use (or free again) the same pointer.
//   - demo_double_free        — free the same allocation twice.
//
// Design questions worth sitting with before writing code (project-charter.md
// Section 10's risk table calls this "expected, not a failure" — so don't
// treat a crash here as something to avoid, treat it as the data point
// you're trying to produce):
//   1. Two of these four demos are, by the C++ standard, undefined behavior
//      — which two? What does "undefined" actually mean in practice (hint:
//      it's not "always crashes" and it's not "always fine" — sit with why
//      that's worse than either)?
//   2. Given #1, how do you let a demo "fail" (crash, corrupt memory) without
//      taking sysdiag_engine's whole process down on every normal run? Does
//      run_all() belong on the default diagnostic path at all, or does it
//      need its own explicit opt-in (a CLI flag in main.cpp, say)? This is
//      also a project-charter.md Section 6 Reliability requirement in
//      disguise — think about where the boundary is.
//   3. What does this class need to hold in its private state to make
//      demo_dangling_pointer and demo_double_free even possible to write?
//      (You need *some* way to keep a pointer around after it's freed on
//      purpose — that's not a bug in your design, it's the setup for the demo.)
//   4. How do you decide `ran_to_completion` for a demo that might segfault
//      the process before it ever returns? (You may not be able to — and if
//      you can't, that itself is worth a comment explaining why.)
//
// Verify with BOTH tools, not just one (project-charter.md Section 7/11) —
// they catch different things and disagree occasionally, which is itself
// instructive:
//   cmake -S cpp -B cpp/build -DENABLE_ASAN=ON && cmake --build cpp/build
//   valgrind --leak-check=full ./cpp/build/sysdiag_engine
// ============================================================================
class MemorySandbox {
public:
    SandboxBugReport demo_clean_cycle();
    SandboxBugReport demo_leak();
    SandboxBugReport demo_dangling_pointer();
    SandboxBugReport demo_double_free();

    // Convenience wrapper the CLI can call — see design question #2 above
    // before wiring this into main.cpp's default path.
    std::vector<SandboxBugReport> run_all();

private:
    // TODO: whatever raw-pointer state the demos above need to hold between
    // calls (design question #3). Nothing declared here on purpose — the
    // shape of this state is part of the exercise, not a given.
};

}  // namespace sysdiag
