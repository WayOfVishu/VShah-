#include "sysdiag/telemetry_json.hpp"

#include <iostream>

namespace sysdiag {

void to_json(nlohmann::json& j, const ProcessMemoryEntry& entry) {
    j = nlohmann::json{
        {"pid", entry.pid},
        {"name", entry.name},
        {"resident_kb", entry.resident_kb},
    };
}

void to_json(nlohmann::json& j, const SystemSnapshot& s) {
    j = nlohmann::json{
        {"cpu_model", s.cpu_model},
        {"cpu_core_count", s.cpu_core_count},
        {"cpu_load_percent", s.cpu_load_percent},
        {"mem_total_kb", s.mem_total_kb},
        {"mem_available_kb", s.mem_available_kb},
        {"top_processes", s.top_processes},
        {"disk_total_kb", s.disk_total_kb},
        {"disk_available_kb", s.disk_available_kb},
    };
}

void to_json(nlohmann::json& j, const SandboxBugReport& r) {
    j = nlohmann::json{
        {"bug_name", r.bug_name},
        {"ran_to_completion", r.ran_to_completion},
        {"notes", r.notes},
    };
}

nlohmann::json build_report(const SystemSnapshot& snapshot,
                             const std::vector<SandboxBugReport>& sandbox_reports) {
    nlohmann::json report;
    report["system"] = snapshot;
    report["memory_sandbox"] = sandbox_reports;
    return report;
}

void emit_report(const nlohmann::json& report) {
    // dump() with no indent argument -> compact single line. Keep it that
    // way: engine_runner.py reads exactly one JSON value from stdout
    // (project-charter.md Section 10 risk: "keep the JSON payload small").
    std::cout << report.dump() << std::endl;
}

}  // namespace sysdiag
