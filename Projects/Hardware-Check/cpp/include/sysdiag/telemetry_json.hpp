#pragma once

// JSON serialization glue: SystemSnapshot / SandboxBugReport -> nlohmann::json
// -> stdout.
//
// Fully implemented (src/telemetry_json.cpp) — this is mechanical structural
// translation (struct field -> JSON key), not a C++ or systems concept worth
// spending your limited project time on. The field names declared here are
// the contract netdiag/schema.py (Python side) expects when it parses this
// binary's stdout — if you add fields to SystemSnapshot/SandboxBugReport
// later, update both sides together.

#include <nlohmann/json.hpp>

#include "sysdiag/memory_sandbox.hpp"
#include "sysdiag/system_info.hpp"

namespace sysdiag {

// nlohmann::json finds these via argument-dependent lookup (ADL) — this is
// the library's standard pattern for teaching it how to serialize a type you
// don't control (see nlohmann/json's README, "Arbitrary types conversions").
void to_json(nlohmann::json& j, const ProcessMemoryEntry& entry);
void to_json(nlohmann::json& j, const SystemSnapshot& snapshot);
void to_json(nlohmann::json& j, const SandboxBugReport& report);

// Combines a SystemSnapshot and however many sandbox demo reports were run
// into the single JSON object this binary prints to stdout. Top-level keys:
// "system" (SystemSnapshot) and "memory_sandbox" (array of SandboxBugReport)
// — matching python/netdiag/schema.py's SYSTEM_KEY / MEMORY_SANDBOX_KEY.
nlohmann::json build_report(const SystemSnapshot& snapshot,
                             const std::vector<SandboxBugReport>& sandbox_reports);

// Writes the JSON to stdout, one compact line, no trailing prose — netdiag.py
// reads this stdout directly (see python/netdiag/engine_runner.py), so
// nothing else should be printed to stdout by this binary.
void emit_report(const nlohmann::json& report);

}  // namespace sysdiag
