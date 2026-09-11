"""
Parse `- [ ] **#TAG** ...` items out of the projects' TODO.md files.

**Start here.** This module has no network, no auth, and no vendor quirks — it
is a pure function from text to a list of dicts, which makes it the one part of
this tool you can develop entirely with tests and no Jira site. Getting it done
first means that when you move to `client.py` you are debugging *one* new thing
(HTTP) rather than two (HTTP and whether your input was ever right).

---

## What you are parsing

Two files, and — usefully for you — they do not use the same format.

Hardware-Check puts the tag alone in bold, description after:

    - [ ] **#SYS-1** `cpp/src/system_info.cpp` — `collect_system_snapshot()`.
      CPU/memory/disk telemetry via `/proc` + `statvfs()`. Do this before
      #MEM-1 if you want an early "it prints real JSON" win, or after ...

Stocks puts the tag *and* a title inside the bold, separated by a middle dot:

    - [ ] **#ML-3 · The zero baseline.** Add "predict 0" and "predict the
          trailing 21-day return" to `baseline_models()`. If none of ...

Handling both is the exercise. Resist the urge to normalise the source files to
match each other — in real work you rarely get to change the input format, and
the second one carries a human-written title you actively want for the Jira
summary.

---

## Three traps, in ascending order of how long they will cost you

**1. Cross-references look exactly like tags.** In the #SYS-1 item above,
`#MEM-1` appears in the body as a reference to a *different* item. A regex for
`#[A-Z]+-\\d+` scanning the whole file finds it and invents a duplicate. The
tag is the one in the bold marker at the start of a list item; everything else
is prose that happens to mention a tag. Your parser needs to care where a match
occurred, not just that it matched.

**2. Items are multi-line.** Every one of them wraps, with continuation lines
indented two or six spaces. Line-by-line parsing that treats each line
independently will truncate every description at the first newline. Deciding
where an item *ends* — next `- [ ]`, next `##` heading, or a blank line? — is
the real work, and the blank-line answer is wrong (Stocks has items with blank
lines inside them).

**3. Checked items.** `- [x]` means done. Whether those should sync at all is
a design question, not an oversight — see #JIRA-9's open question in
`issues.py`. Parse them either way and let the caller decide; a parser that
silently drops data is harder to debug than one that labels it.

**4. Not every tag ends in a number** — and this is the one that will actually
get you, because it fails quietly. `#ML-LOG` and `#ML-LOG-b` are real tags in
Stocks' file. The obvious pattern `#[A-Z]+-\\d+` matches neither, so a parser
using it returns 26 items instead of 28 and looks entirely healthy.

The general lesson is worth more than the specific fix: a parser that finds
*most* of the input is the hardest kind of wrong to notice, because nothing
errors and the output looks plausible. This is why the counts are written down
in `docs/TODO.md` — 13 tagged in Hardware-Check, 15 in Stocks, 27 in League-ML,
55 total. Check against them rather than eyeballing the result.

League-ML uses Stocks' `**#TAG · Title.**` form, so it adds no third format —
but it is the first file where *every* item is tagged, which makes it the
easiest of the three to check a parser against by hand.

---

## The output shape

Whatever you return has to carry enough for `issues.py` to build a Jira issue
and to find it again later. At minimum: the tag, a summary, the body, and
whether it is done. Consider also the **phase heading** the item sits under
(`## Phase 1 — C++ core (target: weeks 3-4)`) and the **source file** — both
map naturally onto Jira fields (a label, an epic, a component) and both are
free to capture now and expensive to add back later once issues exist.
"""

from pathlib import Path
from typing import Any


# ============================================================================
# TODO #JIRA-10 — parse one TODO.md file.
#
# Design questions:
#   1. Regex, or a small line-state machine? A regex that handles multi-line
#      items with two indent styles gets unreadable fast; a loop that tracks
#      "am I inside an item" stays legible. Try the regex first if you want —
#      finding out *why* it gets ugly is worth more than being told.
#   2. What is the summary for a Hardware-Check item, where the bold contains
#      only the tag? The first sentence? The first line? Up to the first
#      period? Jira summaries are single-line and long ones render badly, so
#      there is a real length constraint here, not just an aesthetic one.
#   3. What do you do with an item whose bold marker has no tag at all? Both
#      files have some (Phase 6 of Hardware-Check, the frontend items in
#      Stocks). Skip them, or synthesise a tag? Skipping is defensible —
#      untagged items cannot be matched idempotently later, which is exactly
#      the property #JIRA-8 depends on.
# ============================================================================
def parse_todo_file(path: Path) -> list[dict[str, Any]]:
    """Parse one TODO.md into a list of item dicts."""
    raise NotImplementedError("parse_todo_file() is not implemented yet — see #JIRA-10")


# ============================================================================
# TODO #JIRA-11 — parse every configured source.
#
# Thin wrapper over #JIRA-10 across config.TODO_SOURCES.
#
# Design question worth two minutes: tags are unique within a file, but are
# they unique *across* files? Hardware-Check uses #SYS/#MEM/#NET/#AI, Stocks
# uses #ML, and League-ML uses #ING/#FEAT/#DL/#EVAL/#REC/#LML — so today the
# answer is yes, by luck, not by design. League-ML's #ING-2 (the one
# `gemini_client.py` references) now exists; if something else later also
# picks #ING — or #EVAL, or #FEAT, which are generic enough that it will — two
# different items map to one Jira issue and one silently overwrites the
# other's identity.
#
# Should this detect collisions and raise? Namespace tags by project? Or just
# document the assumption and move on? All three are legitimate; the one that
# is not is discovering it after the board is populated.
# ============================================================================
def parse_all() -> list[dict[str, Any]]:
    """Parse every file in config.TODO_SOURCES."""
    raise NotImplementedError("parse_all() is not implemented yet — see #JIRA-11")
