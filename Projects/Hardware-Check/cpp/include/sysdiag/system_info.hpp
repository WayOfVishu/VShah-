#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace sysdiag {

// One process's contribution to the per-process memory breakdown
// (Functional Requirement 5.1: "per-process memory usage").
struct ProcessMemoryEntry {
    int pid = 0;
    std::string name;
    std::uint64_t resident_kb = 0;  // resident set size, in KB
};

// Everything the CLI/JSON layer needs from one diagnostic pass. This struct
// is deliberately just data — plain fields, no behavior — so it's trivial
// to serialize (see telemetry_json.hpp) and trivial to reason about
// independently of how each field got filled in.
struct SystemSnapshot {
    // CPU
    std::string cpu_model;
    unsigned int cpu_core_count = 0;
    double cpu_load_percent = 0.0;  // instantaneous or short-window average — your call, document which

    // Memory (all in KB, matching /proc/meminfo's native unit — no reason
    // to convert and reintroduce rounding error before the JSON boundary)
    std::uint64_t mem_total_kb = 0;
    std::uint64_t mem_available_kb = 0;
    std::vector<ProcessMemoryEntry> top_processes;  // however many you decide is a reasonable "top N"

    // Disk (the filesystem backing the current working directory is enough for v1 —
    // Instructions.md/project-charter.md doesn't ask for a full mount-table sweep)
    std::uint64_t disk_total_kb = 0;
    std::uint64_t disk_available_kb = 0;
};

// Collects one SystemSnapshot by reading the live system state.
//
// TODO (Phase 1, weeks 3-4 — see docs/TODO.md #SYS-1). This is the "OS-level
// system interaction" primary learning objective from project-charter.md
// Section 2 — implemented in src/system_info.cpp, not here. This header
// only declares the shape.
SystemSnapshot collect_system_snapshot();

}  // namespace sysdiag
