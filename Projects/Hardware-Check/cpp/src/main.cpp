// sysdiag_engine — thin CLI wrapper around libsysdiag.
//
// Fully implemented (mechanical wiring, not a learning objective) — but
// note it calls straight into collect_system_snapshot() and MemorySandbox,
// both of which currently throw std::logic_error until docs/TODO.md
// #SYS-1 / #MEM-1 are done. That's expected: this binary won't produce
// real output until those land. Running it now is still useful — it tells
// you exactly which TODO you're blocked on, via stderr.
//
// Usage:
//   sysdiag_engine                    # system snapshot only, printed as JSON to stdout
//   sysdiag_engine --memory-demo=all  # also runs every MemorySandbox demo
//   sysdiag_engine --memory-demo=leak # runs just one named demo
//
// --memory-demo is opt-in, not part of the default pass, on purpose — see
// memory_sandbox.hpp's design question #2. Two of the four demos are
// undefined behavior by design; you don't want those on the path netdiag.py
// invokes for an ordinary diagnostic run.

#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>

#include "sysdiag/memory_sandbox.hpp"
#include "sysdiag/system_info.hpp"
#include "sysdiag/telemetry_json.hpp"

namespace {

std::optional<std::string> parse_memory_demo_flag(int argc, char** argv) {
    const std::string prefix = "--memory-demo=";
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg.rfind(prefix, 0) == 0) {
            return arg.substr(prefix.size());
        }
        if (arg == "--memory-demo") {
            return "all";
        }
    }
    return std::nullopt;
}

std::vector<sysdiag::SandboxBugReport> run_requested_demos(const std::string& which) {
    sysdiag::MemorySandbox sandbox;
    if (which == "all") {
        return sandbox.run_all();
    }
    if (which == "clean_cycle") {
        return {sandbox.demo_clean_cycle()};
    }
    if (which == "leak") {
        return {sandbox.demo_leak()};
    }
    if (which == "dangling_pointer") {
        return {sandbox.demo_dangling_pointer()};
    }
    if (which == "double_free") {
        return {sandbox.demo_double_free()};
    }
    throw std::invalid_argument("unknown --memory-demo value: " + which);
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const sysdiag::SystemSnapshot snapshot = sysdiag::collect_system_snapshot();

        std::vector<sysdiag::SandboxBugReport> sandbox_reports;
        if (const auto demo = parse_memory_demo_flag(argc, argv)) {
            sandbox_reports = run_requested_demos(*demo);
        }

        const nlohmann::json report = sysdiag::build_report(snapshot, sandbox_reports);
        sysdiag::emit_report(report);
        return 0;
    } catch (const std::exception& e) {
        // Deliberately stderr, not stdout — engine_runner.py on the Python
        // side reads stdout as JSON-or-nothing (project-charter.md Section 6
        // Reliability requirement: one bad reading shouldn't take down the
        // whole tool, but it does need to be visible to whoever's debugging).
        std::cerr << "sysdiag_engine error: " << e.what() << std::endl;
        return 1;
    }
}
