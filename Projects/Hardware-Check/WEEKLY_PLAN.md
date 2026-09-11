# Weekly Plan — 3-4 Hours/Week

**What this file is:** a session-by-session execution guide, scoped to what
you can realistically do in **one 3-4 hour block per week**. `docs/working-
plan.md` describes the project in six phases (Practice / Early POC / Keep
working / Beta / Improve with feedback / Finish); this file is the layer
underneath that answers "okay, but what do I actually open and do this
Tuesday night." `docs/TODO.md` is the task-ID index; this file is the
task IDs cut into pieces small enough to survive a real 3-4 hour week.

**Read this part before the schedule below — it changes what "12 weeks"
means:**

`docs/working-plan.md`'s 12-week arc was paced for something closer to
10-15 hours/week. At a genuine 3-4 hours/week, the same amount of *work*
takes roughly **3-4x longer in calendar time**. This document's session
count below comes out to roughly **35 sessions**, which at one session a
week is **around 8-9 months**, not 12 weeks. That's not this project
failing to fit a template — it's the honest arithmetic of the same scope
at a slower, sustainable pace. `docs/project-charter.md` §8 (Constraints) already
says this project needs to survive being paused for weeks at a time and
still resume — a slow, steady 8-9 months that actually lands, next to a
CS Master's application timeline, beats a rushed 12 weeks that stalls out
in week 3. Nothing about the scope in `docs/project-charter.md` needs to shrink;
only the calendar does.

If some week you get 2 sessions instead of 1 (a slow week at work, a long
weekend), just do the next two rows — nothing here is calendar-locked, it's
ordered, not dated.

## How to read each entry

Every session has the same four parts:
- **Open** — the exact files, in order, to have on screen. Read before you type.
- **Do** — the one thing this session is actually for. Scoped to fit 3-4 hours *including* the debugging time that thing will actually cost you — if it feels like too little, that's the point, not a mistake.
- **Don't** — the adjacent thing you'll be tempted to also start. Leave it for its own session.
- **Check** — how you know you're actually done, not just "done typing."

---

## Part 1 — Orientation (1 session)

### Session 1 — find out where you actually stand
**Open, in this order:**
1. `README.md` (whole file, ~5 min)
2. `docs/project-charter.md` §0-§2 (Document History, Overview, Learning Objectives) — stop there, the rest can wait
3. `docs/working-plan.md` (whole file — the map this document zooms into)
4. `docs/TODO.md` (skim only — see the shape, don't pick a task yet)

**Do:**
- Confirm WSL2 + an Ubuntu distro is installed and working. Inside it, verify:
  ```bash
  g++ --version      # need GCC 10+ for real C++20 support
  cmake --version    # need 3.20+
  valgrind --version
  ```
- Try building the repo exactly as it stands right now (it's expected to fail meaningfully, not cleanly):
  ```bash
  cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Debug
  cmake --build cpp/build
  ./cpp/build/sysdiag_engine
  ```

**Don't:** open any `.cpp` file yet. This session is entirely environment + orientation.

**Check:** the build succeeds, and running the binary prints something like
`sysdiag_engine error: collect_system_snapshot() is not implemented yet —
see docs/TODO.md #SYS-1` to your terminal, then exits with a non-zero code.
Seeing that *exact kind* of failure means your whole toolchain works —
that's this session's real success condition. If you got a different
error (compiler too old, CMake can't fetch `nlohmann/json` over the
network, `valgrind: command not found`), fixing that becomes next
session's task before anything else.

---

## Part 2 — C++ fundamentals, outside the repo (3 sessions)

Nothing in this part touches `hardware-check/` code. `cpp/include/sysdiag/
memory_sandbox.hpp` explicitly expects you to have already felt these bugs
happen before you write the real demos — that's what these sessions are for.

### Session 2 — pointers, by hand
**Open:** `cpp/include/sysdiag/memory_sandbox.hpp` (read only — the four
demo names, the design questions above the class, the "nothing declared
here on purpose" comment on the private section).

**Do:** in a scratch file (anywhere outside this repo — your scratchpad
directory is fine), write and run three tiny standalone programs:
1. `new int`, print it, `delete` it.
2. `new int[10]`, write to a few slots, `delete[]` it.
3. `new` something and deliberately **don't** delete it — run it, and
   notice that nothing visibly bad happens. That invisibility is the
   entire reason a leak needs a tool to catch, not your eyes.

**Don't:** open `cpp/src/memory_sandbox.cpp` yet.

**Check:** you can say out loud, in your own words, the difference between
stack and heap allocation, and why a memory leak doesn't look like an
error when the program runs.

### Session 3 — watching the tools catch what you can't see
**Do:** take session 2's leak program.
```bash
g++ -g leak.cpp -o leak && valgrind --leak-check=full ./leak
g++ -g -fsanitize=address -fno-omit-frame-pointer leak.cpp -o leak_asan && ./leak_asan
```
Read the output from both, slowly. Then write a dangling-pointer scratch
program (`delete` something, then use the pointer again) and run it
through both tools too.

**Don't:** touch the real sandbox class yet — this is still scratch code.

**Check:** you can point to the exact line in Valgrind's output that names
your leak's allocation site, and describe (even loosely) what ASan
reported differently for the dangling-pointer case vs. the leak.

### Session 4 — reading `/proc` by hand
**Open:** `cpp/src/system_info.cpp` (the stub + its full comment block),
`cpp/include/sysdiag/system_info.hpp` (the `SystemSnapshot` fields).

**Do:** forget C++ for this session. In a WSL2 shell:
```bash
man proc
cat /proc/meminfo | head -5
cat /proc/cpuinfo | head -20
cat /proc/stat | head -3
free -h
nproc
```
Match what you see to the field names in `SystemSnapshot`. Write yourself
a one-line note next to each field for *which* `/proc` line it comes from
— you'll want that note in session 6.

**Don't:** open an editor for `.cpp` files this session — this is a
reading/reconnaissance session, and it's a real session on its own at this
pace.

**Check:** for every field in `SystemSnapshot`, you can point to the exact
line of a `/proc` file (or `statvfs`, for disk) it comes from.

---

## Part 3 — `#SYS-1`: system telemetry (5 sessions)

One field group per session. Each session: temporarily hardcode
`collect_system_snapshot()` to return everything else as default so you
can build and see real numbers as you go — don't wait until the whole
function is done to run it once.

### Session 5 — memory fields
**Open:** `cpp/src/system_info.cpp`.
**Do:** `mem_total_kb`, `mem_available_kb` from `/proc/meminfo`.
**Don't:** CPU, disk, or process fields yet.
**Check:** your program's numbers roughly match `free -h`'s, run at the same moment.

### Session 6 — CPU identity fields
**Do:** `cpu_model`, `cpu_core_count` from `/proc/cpuinfo` — mind design
question 1 in the file's comment (hyperthreads repeat a full stanza; don't
silently double-count them without deciding on purpose).
**Check:** `cpu_core_count` matches `nproc`.

### Session 7 — CPU load
**Do:** `cpu_load_percent` — pick `/proc/stat` (delta between two reads) or
`/proc/loadavg` (design question 3), implement one, and leave a comment
saying which you picked and why.
**Check:** the number is in the right ballpark against `top`/`htop` watched
at the same time.

### Session 8 — disk
**Open:** `<sys/statvfs.h>` reference (this one's a real syscall wrapper,
not a `/proc` read — notice the difference).
**Do:** `disk_total_kb`, `disk_available_kb`.
**Check:** compare against `df -h .`.

### Session 9 — the hard one: per-process memory, then wire it all together
**Do:** `top_processes` via iterating numeric `/proc/[pid]` directories and
reading `VmRSS:` from each `status` file — handle a process disappearing
mid-iteration explicitly (design question 2), don't let it crash the whole
snapshot. Then remove all the hardcoding from sessions 5-8 and assemble
the real `collect_system_snapshot()`.
**Check:** full clean build, `./cpp/build/sysdiag_engine` prints a complete
JSON snapshot with no default/zero fields left over. Check off `#SYS-1` in
`docs/TODO.md`.

---

## Part 4 — `#MEM-1`: the memory sandbox (6 sessions)

This is *the* module. Don't compress it to catch up on a "schedule" — there
isn't a real one here, just this list, and this list assumes you take the
time this part actually needs.

### Session 10 — design on paper, not in code
**Open:** `cpp/include/sysdiag/memory_sandbox.hpp`, design question 3.
**Do:** no code this session. Sketch (on paper, or as a comment block) what
private state `MemorySandbox` needs to hold so `demo_dangling_pointer` and
`demo_double_free` are even possible to write — you need some way to keep
a pointer around *after* it's been freed on purpose.
**Check:** you can explain your sketch before you type a single line of
the real class.

### Session 11 — `demo_clean_cycle`
**Do:** implement the control case only — allocate, use, free, correctly.
**Check:** ASan and Valgrind both report **zero** complaints. If either
complains, this "clean" case has a real bug — fix it before moving on;
every later demo gets compared against this one being actually clean.

### Session 12 — `demo_leak`
**Do:** implement.
**Check:** both tools report a leak. If neither does, it isn't actually
leaking — find out why before moving on (a common cause: something else in
scope still holds/frees it).

### Session 13 — `demo_dangling_pointer`
**Do:** implement (this is design question 1's territory — confirm for
yourself which of the four demos are undefined behavior and why that's a
stronger claim than "usually crashes").
**Check:** run it under ASan several times in a row. Note whether the
behavior is consistent between runs — the header's whole point about
undefined behavior is that it might not be.

### Session 14 — `demo_double_free`
**Do:** implement.
**Check:** ASan/Valgrind flag this one distinctly from the leak and the
dangling-pointer case — note in a comment what's actually different in
each tool's report.

### Session 15 — `run_all()`, and closing the phase out
**Do:** implement `run_all()`. Confirm the already-built `--memory-demo`
flag in `cpp/src/main.cpp` now genuinely works end to end for each demo
name and for `all`. Run `--memory-demo=all` under both ASan and Valgrind.
Then run the binary with **no** flag and confirm the risky demos do
*not* execute (design question 2 — this was the reason the flag is
opt-in in the first place).
**Check:** `docs/TODO.md` `#MEM-1` checked off. This closes out
`docs/working-plan.md`'s "Early POC" phase — 15 sessions in, roughly
15 weeks/~3.5 months from session 1 at this pace. That's expected, not slow.

---

## Part 5 — `#MEM-2`/`#MEM-3`: the smart-pointer refactor (4 sessions)

### Session 16 — protect the "before"
**Do:** before changing anything, make sure the raw-pointer version from
Part 4 survives somewhere you can diff against later — a git branch, tag,
or a copied file. `docs/project-charter.md` §13's Acceptance Criteria wants a real
before/after writeup; you can't write that without an actual "before."
**Check:** you can locate the untouched raw-pointer version on demand.

### Session 17 — refactor the two safe demos
**Do:** `demo_clean_cycle` and `demo_leak` → `std::unique_ptr`. Notice (and
comment on) whether `demo_leak` is even still *possible* to write once
you're using RAII — that observation is worth more than the code.

### Session 18 — refactor the two UB demos
**Do:** `demo_dangling_pointer`/`demo_double_free` → smart pointers. Same
prompt: what changes about what you can even demonstrate?

### Session 19 — write the comparison
**Do:** write `README.md`'s Results section, before/after — include real
ASan/Valgrind excerpts from both versions, not just prose claims.
**Check:** `#MEM-2`/`#MEM-3` checked off in `docs/TODO.md`.

---

## Part 6 — network probes (5 sessions)

### Session 20 — `ping_probe.py`, happy path
**Open:** `python/netdiag/ping_probe.py`.
**Do:** get `subprocess.run(["ping", "-c", ...])` working and print the raw
output. Don't parse it into numbers yet.

### Session 21 — `ping_probe.py`, finish it
**Do:** parse avg/min/max latency (design question 1 — summary line vs.
per-line parsing), handle an unreachable host (design question 2).
**Check:** `docs/TODO.md` `#NET-1` checked off.

### Session 22 — `dns_probe.py`
**Open:** `python/netdiag/dns_probe.py`.
**Do:** implement `measure_dns()` end to end — it's one function, but read
design questions 1-3 before picking `getaddrinfo` vs. `gethostbyname`.
**Check:** `#NET-2` checked off; a bad hostname doesn't crash your test run.

### Session 23 — `port_scan.py`, sequential
**Open:** `python/netdiag/port_scan.py`.
**Do:** a correct **sequential** TCP connect scan. Ignore concurrency
entirely this session (design question 2 explicitly says don't reach for
threads until sequential is right).
**Check:** un-skip `python/tests/test_port_scan.py`'s test and get it green.

### Session 24 — `port_scan.py`, finish + `dns_probe.py` test
**Do:** tune the timeout (design question 3), decide on concurrency or
not, and be honest with yourself about whether it's worth the added
complexity at this stage. Un-skip `test_dns_probe.py`'s two tests.
**Check:** `#NET-3` checked off, both probe test files green.

---

## Part 7 — `#NET-4`: the IPC boundary (2 sessions)

### Session 25 — `engine_runner.py`, happy path
**Open:** `python/netdiag/engine_runner.py`, and re-read
`cpp/src/main.cpp`'s comment on stdout/stderr/exit-code conventions.
**Do:** `subprocess.run` + `json.loads` for the success case only.

### Session 26 — `engine_runner.py`, failure paths
**Do:** missing binary, non-zero exit, timeout, malformed JSON (design
questions 2-4).
**Check:** un-skip `python/tests/test_engine_runner.py`, both tests green.
`#NET-4` checked off. `python hwcheck.py --raw --no-ai` should now print
one merged JSON payload with no crashes — the whole non-AI pipeline works.

---

## Part 8 — Gemini integration (5 sessions)

### Session 27 — get a key, design the prompt
**Do:** register a free key at aistudio.google.com, copy `.env.example` to
`.env`. In `python/ai_analyzer/prompt_builder.py`, write the prompt text
and sketch the response schema (design questions 1-2).

### Session 28 — `gemini_client.py`, happy path
**Open:** `python/ai_analyzer/gemini_client.py` (the built `get_client()`
part first, then the `call_gemini()` stub).
**Do:** get one real, successful API call working — no retry logic yet.

### Session 29 — `gemini_client.py`, retry/backoff
**Do:** deliberately hammer the free-tier rate limit until you actually
see a 429, then build the retry/backoff loop against a real observed
failure instead of a hypothetical one.
**Check:** `#AI-2` checked off.

### Session 30 — `response_parser.py`
**Open:** `python/ai_analyzer/response_parser.py`.
**Do:** implement `parse_analysis()`, including at least one deliberately
malformed input to confirm your failure handling actually triggers.
**Check:** `#AI-1`/`#AI-3` checked off.

### Session 31 — the first real end-to-end run
**Do:** `python hwcheck.py` for real, no flags. This is the first moment
all three languages/modules connect in one run.
**Check:** you get a real plain-language summary back, printed and (with
`--export json`) written to `data/reports/`.

---

## Part 9 — Beta, feedback, and finishing (4 sessions)

### Session 32 — get a real second pair of eyes
**Do:** hand the CLI to a classmate or mentor. Watch them run it without
help. Take notes on what confused them or broke.

### Session 33-34 — act on it
**Do:** fix what session 32 surfaced. This is also the point
`docs/project-charter.md` §14 flags for revisiting the C++20 → C++23 question —
you now have a real working baseline to weigh that upgrade against.

### Session 35 — finish
**Do:** write `README.md`'s Results/known-limitations sections with real,
non-placeholder numbers. Confirm a completely clean checkout builds and
runs. Walk through `docs/project-charter.md` §13's Acceptance Criteria line by
line and check each one honestly — don't check a box you're not sure of.
**Check:** every `docs/TODO.md` item outside Phase 7 (the GUI, deliberately
out of this plan) is checked off.

---

## Total, plainly

~35 sessions. At one 3-4 hour session/week, that's roughly **35 weeks —
about 8-9 months** from Session 1 to a finished v1. That number is the
point of this document: it's what "3-4 hours a week" actually costs for
this scope, stated up front instead of discovered halfway through by
missing an unstated deadline. Revisit this file after Part 4 (the memory
sandbox) — by then you'll have real per-session data on how long things
actually take *you*, which will be a better estimate than this one for
everything after it.
