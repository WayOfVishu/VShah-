#include "sysdiag/system_info.hpp"

#include <stdexcept>

// TODO (Phase 1, weeks 3-4 — docs/TODO.md #SYS-1)
//
// The "OS-level system interaction" primary learning objective
// (project-charter.md Section 2). Everything you need is a Linux text
// pseudo-file you can open with a plain std::ifstream and parse line by
// line — no special API, no root required. Read `man proc` before writing
// any code; it documents the exact format of every file below.
//
// What each piece of SystemSnapshot maps to:
//   cpu_model, cpu_core_count   -> /proc/cpuinfo (one stanza per logical core;
//                                  "model name" and counting stanzas gets you both)
//   cpu_load_percent            -> /proc/stat's first "cpu " line, OR
//                                  /proc/loadavg if you'd rather report load
//                                  average instead of an instantaneous
//                                  percentage — pick one and say which in a
//                                  comment, they're not the same number
//   mem_total_kb, mem_available_kb -> /proc/meminfo ("MemTotal:", "MemAvailable:" —
//                                  note MemAvailable, not MemFree; they differ
//                                  and MemAvailable is the one that actually
//                                  answers "how much can a new process use")
//   top_processes                -> /proc/[pid]/status ("VmRSS:") for each pid
//                                  directory under /proc — iterating "every
//                                  numeric directory under /proc" is itself
//                                  the first design decision here
//   disk_total_kb, disk_available_kb -> statvfs() on "." (from <sys/statvfs.h>) —
//                                  this one isn't a /proc file, it's a real
//                                  POSIX syscall wrapper; worth noticing the
//                                  difference from the /proc-based fields above
//
// Design questions:
//   1. /proc/cpuinfo repeats a full stanza per logical core (hyperthreads
//      count as separate stanzas) — how do you get a core *count* out of
//      that without just counting "model name" occurrences and accidentally
//      double-counting hyperthreads? Does it matter for this project?
//   2. What happens to this whole function if /proc/[pid]/status disappears
//      between you listing /proc's directories and you opening that specific
//      file (a process can exit in that window)? project-charter.md's
//      Reliability requirement (Section 6) says a bad reading shouldn't
//      crash the whole run — where does that get handled here vs. one level
//      up in main.cpp?
//   3. cpu_load_percent: instantaneous snapshot (needs two /proc/stat reads
//      a short interval apart and a delta) or the kernel's rolling load
//      average (one read, already smoothed)? Both are defensible; document
//      whichever you pick so main.cpp's caller isn't guessing.
//
// Reference: Beej-adjacent for /proc specifically doesn't exist, but
// `man proc` and OSTEP (project-charter.md Section 11) both cover this well.

namespace sysdiag {

SystemSnapshot collect_system_snapshot() {
    throw std::logic_error(
        "collect_system_snapshot() is not implemented yet — see docs/TODO.md #SYS-1");
}

}  // namespace sysdiag
