#include "sysdiag/memory_sandbox.hpp"

#include <stdexcept>

// TODO (Phase 1, weeks 3-4 — docs/TODO.md #MEM-1)
// See the design questions and constraints in
// include/sysdiag/memory_sandbox.hpp above the class declaration — read
// those before writing any code here. This file is intentionally left with
// nothing but stubs: no member layout, no helper functions, no partial
// implementation to react to. That's not an oversight.
//
// One implementation note, not a design question — a plain fact you need
// regardless of how you design the rest: `delete` on a raw pointer does
// NOT set that pointer to nullptr. It stays pointing at memory that's now
// unowned. That's what makes demo_dangling_pointer and demo_double_free
// possible to write at all — the pointer variable itself doesn't know
// anything happened.

namespace sysdiag {

SandboxBugReport MemorySandbox::demo_clean_cycle() {
    throw std::logic_error("demo_clean_cycle() is not implemented yet — see docs/TODO.md #MEM-1");
}

SandboxBugReport MemorySandbox::demo_leak() {
    throw std::logic_error("demo_leak() is not implemented yet — see docs/TODO.md #MEM-1");
}

SandboxBugReport MemorySandbox::demo_dangling_pointer() {
    throw std::logic_error(
        "demo_dangling_pointer() is not implemented yet — see docs/TODO.md #MEM-1");
}

SandboxBugReport MemorySandbox::demo_double_free() {
    throw std::logic_error("demo_double_free() is not implemented yet — see docs/TODO.md #MEM-1");
}

std::vector<SandboxBugReport> MemorySandbox::run_all() {
    throw std::logic_error("run_all() is not implemented yet — see docs/TODO.md #MEM-1");
}

}  // namespace sysdiag
