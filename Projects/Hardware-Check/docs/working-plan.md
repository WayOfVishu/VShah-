# Working Plan — 12 Weeks

This is the canonical calendar (also reproduced in `docs/project-charter.md`
Section 12) — `docs/TODO.md` is the detailed, checkable task list; this
document is the pacing. It supersedes the original draft's phase numbering
(0 through 7) with a plain 6-bucket 12-week arc, decided 2026-08-25.

**This 12-week arc assumes something like 10-15 hours/week.** At a real
3-4 hours/week, use `../WEEKLY_PLAN.md` instead for pacing — it breaks the
same phases into ~35 session-sized steps and is honest that the resulting
calendar is closer to 8-9 months than 12 weeks. Treat this file as the
map of *what* happens in each phase; treat `WEEKLY_PLAN.md` as *when*,
given your actual available time.

| Weeks | Stage | Goal | What's already built vs. yours to build |
|---|---|---|---|
| 1-2 | **Practice** | C++ refresher — syntax, pointers, stack vs. heap, what RAII means before you implement it (project-charter.md Section 12's original "Phase 0" reasoning still applies: starting straight into real project code with zero C++ under your belt is how this stalls in week 2). Also: small throwaway Python scripts — `subprocess`, `socket.getaddrinfo`, reading/writing JSON — nothing that ships, just getting the tools to feel normal in your hands. Set up WSL2 if you haven't, confirm `cmake`/`g++`/`valgrind` are installed there. | Repo scaffolding, `netdiag/config.py`, `netdiag/schema.py`, `netdiag/report_writer.py`, `cli/main.py`, the full CMake build (`cpp/CMakeLists.txt`) are done. Nothing to build yet — deliberately a ramp-up window. |
| 3-4 | **Early POC** | `sysdiag_engine` runs standalone (no Python involved yet) and prints real JSON: system/memory/disk telemetry, plus the four raw-pointer memory-sandbox demos, ASan- and Valgrind-clean where they're supposed to be clean (and confirmed *not* clean where they're supposed to demonstrate a bug). | `#SYS-1`, `#MEM-1` (`docs/TODO.md`). This is the hardest, most important phase in the whole project — the primary learning objective lives here. Don't compress it to stay "on schedule" for later weeks; a rushed memory sandbox defeats the point of building one. |
| 5-6 | **Keep working** | Two parallel tracks: (a) refactor the sandbox to smart pointers and write the before/after comparison while the raw-pointer version is still fresh in your head; (b) build the three network probes. By the end of week 6, `python hwcheck.py --raw --no-ai` should print one merged JSON payload combining C++ + Python telemetry with no crashes. | `#MEM-2`, `#MEM-3`, `#NET-1`, `#NET-2`, `#NET-3`, `#NET-4`. |
| 7-8 | **Beta** | Gemini integration lands — structured prompt, the actual API call with retry/backoff, response parsing. By end of week 8, `python hwcheck.py` runs the *entire* pipeline end to end and prints a real plain-language summary. This is v1. Get it in front of someone (classmate, mentor — anyone who'll actually try to break it) before week 8 ends. | `#AI-1`, `#AI-2`, `#AI-3`. Acceptance Criteria (project-charter.md Section 13) should hold by the end of this window. |
| 9-10 | **Improve with feedback** | Act on whatever the week-8 beta tester found confusing, broken, or unconvincing. Typical targets: CLI output clarity, whether a probe's error handling actually degrades gracefully instead of crashing the run, whether the README's before/after memory writeup actually makes sense to someone who wasn't in your head while you wrote it. This is also the point at which to evaluate the C++20 → C++23 question (project-charter.md Section 7/Open Decisions) — you now have a working baseline to weigh the upgrade against, instead of guessing in the abstract. | Mostly revision, not new modules. Decide the C++23 question here, don't just leave it open indefinitely. |
| 11-12 | **Finish** | Freeze scope. Polish `README.md`'s Results section with honest, real numbers (no placeholders — project-charter.md Section 6 rules out inflated claims and that cuts both ways). Confirm a clean checkout builds and runs end to end. Phase 7 (the GUI) is explicitly **not** part of this 12-week window — it's real, per Open Decision #1, but it starts after this window closes, not squeezed into it. | Housekeeping items in `docs/TODO.md`. |

## Ground rules (from project-charter.md, worth restating)

- **Section 6 (Reliability):** one bad reading — a missing sensor, a
  timed-out ping, a malformed Gemini response — should never crash the
  whole run. Nearly every TODO module's design questions come back to this.
- **Section 10 risk table:** memory bugs while learning C++ are *expected*,
  not a sign something's wrong. Isolate the risky code in the sandbox
  module (it already is, by construction) and verify with both ASan and
  Valgrind constantly, not just at the end of Phase "Early POC."
- **Section 3:** the out-of-scope list (full cross-platform, GUI-for-now,
  raw packet capture, kernel-level anything) is a real boundary. Revisit it
  only after v1 (end of "Beta," week 8) actually works.
- If weeks 3-4 or 5-6 slip, that's expected and already budgeted for
  (project-charter.md Section 8, "Time" constraint) — don't compress the
  memory-management or networking learning time to protect the Gemini
  weeks. A polished AI summary of broken/fake telemetry isn't worth more
  than an honest, working core.
