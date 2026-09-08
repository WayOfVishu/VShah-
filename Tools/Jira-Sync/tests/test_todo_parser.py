"""
Scaffolded tests for jira_sync.todo_parser — skipped until #JIRA-10/#JIRA-11
land. Fixtures built, assertions yours.

These are the tests to write first in the whole tool. The parser is a pure
function, so every one of these runs in milliseconds with no network, no
credentials and no Jira site — which means you can develop the parser
test-first properly, rather than test-first in the aspirational sense.

The fixtures below are real excerpts, copied from the actual TODO.md files
rather than invented. That matters: made-up fixtures test the format you
imagined, and the whole difficulty here is that the real format has two
variants and a trap in it.
"""

import textwrap

import pytest

from jira_sync import todo_parser


@pytest.fixture
def hardware_check_excerpt(tmp_path):
    """Hardware-Check's format: tag alone in bold, prose after. Note that the
    #SYS-1 item's body *mentions* #MEM-1 — that cross-reference is trap 1 from
    the module docstring, and it is in here on purpose."""
    content = textwrap.dedent("""\
        ## Phase 1 — C++ core (target: weeks 3-4)

        - [ ] **#SYS-1** `cpp/src/system_info.cpp` — `collect_system_snapshot()`.
          CPU/memory/disk telemetry via `/proc` + `statvfs()`. Do this before
          #MEM-1 if you want an early "it prints real JSON" win, or after if you'd
          rather get the harder module out of the way first — order doesn't matter
          functionally, they're independent.
        - [ ] **#MEM-1** `cpp/src/memory_sandbox.cpp` + the four `MemorySandbox`
          methods declared in `cpp/include/sysdiag/memory_sandbox.hpp`. **The
          primary point of this entire project.**

        ## Phase 2 — Refactor (target: week 5)

        - [x] **#MEM-2** Refactor the Phase 1 raw-pointer sandbox to
          `std::unique_ptr`/`std::shared_ptr`.
        """)
    path = tmp_path / "hardware_todo.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def stocks_excerpt(tmp_path):
    """Stocks' format: tag AND title inside the bold, separated by ' · '.
    Also has an item with a blank line inside it — trap 2."""
    content = textwrap.dedent("""\
        ## Phase 1 — before you model anything

        - [ ] **#ML-3 · The zero baseline.** Add "predict 0" and "predict the
              trailing 21-day return" to `baseline_models()`. If none of Ridge /
              RF / GBM beat *predict zero* on R², the pipeline is not adding
              information.
              **This is the single most important comparison in the project.**

        - [ ] **#ML-0 · Does Gemini beat VADER?** The one experiment this rewrite
              created, and it should run before any tuning.
        """)
    path = tmp_path / "stocks_todo.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.skip(reason="todo_parser.parse_todo_file is not implemented yet — see #JIRA-10")
def test_extracts_every_tagged_item(hardware_check_excerpt):
    # TODO: assert exactly three items come back — #SYS-1, #MEM-1, #MEM-2.
    #
    # Assert the *count* as well as the membership. "#SYS-1 is in there" passes
    # against a parser that also invented a fourth item from the #MEM-1
    # cross-reference in #SYS-1's body; "there are exactly three" does not.
    # This is the assertion that catches trap 1.
    pytest.fail("write me")


@pytest.mark.skip(reason="todo_parser.parse_todo_file is not implemented yet — see #JIRA-10")
def test_cross_reference_in_body_is_not_a_separate_item(hardware_check_excerpt):
    # TODO: the explicit version of the check above, worth its own test because
    # it will fail for a specific, findable reason.
    #
    # #SYS-1's body contains the literal text "#MEM-1". There IS a real #MEM-1
    # item in this fixture, so a naive parser produces two entries for it — one
    # real, one hallucinated from the prose — and a `len(items) == 3` assertion
    # somewhere else might still pass by coincidence if it also dropped
    # something. Assert here that #MEM-1 appears exactly once.
    pytest.fail("write me")


@pytest.mark.skip(reason="todo_parser.parse_todo_file is not implemented yet — see #JIRA-10")
def test_multiline_body_is_captured_whole(hardware_check_excerpt):
    # TODO: #SYS-1's description spans five lines. Assert the captured body
    # contains text from the LAST line ("they're independent"), not just the
    # first.
    #
    # Testing the last line rather than the first is deliberate: a parser that
    # truncates at the newline passes any assertion about the beginning.
    pytest.fail("write me")


@pytest.mark.skip(reason="todo_parser.parse_todo_file is not implemented yet — see #JIRA-10")
def test_blank_line_inside_an_item_does_not_end_it(stocks_excerpt):
    # TODO: trap 2. #ML-3's body has a blank line before "**This is the single
    # most important comparison**". Assert that sentence is part of #ML-3's
    # body and did not become a separate item or get dropped.
    pytest.fail("write me")


@pytest.mark.skip(reason="todo_parser.parse_todo_file is not implemented yet — see #JIRA-10")
def test_handles_the_stocks_tag_and_title_format(stocks_excerpt):
    # TODO: assert the tag parses as "#ML-3" and the summary is "The zero
    # baseline." — i.e. the ' · ' separator was understood and the title did
    # not end up glued to the tag.
    #
    # This is where design question 2 in the module gets settled: Stocks items
    # hand you a human-written title, Hardware-Check items do not. Whatever
    # your summary rule is, it has to produce something sensible for both, and
    # this test plus the one above are where you find out if it does.
    pytest.fail("write me")


@pytest.mark.skip(reason="todo_parser.parse_todo_file is not implemented yet — see #JIRA-10")
def test_checked_items_are_marked_done_not_dropped(hardware_check_excerpt):
    # TODO: #MEM-2 is `- [x]`. Assert it is returned AND flagged as done.
    #
    # Returned, not dropped — see trap 3. Whether done items get synced is
    # issues.py's decision (#JIRA-9); the parser's job is to report what the
    # file says, not to decide what the caller does about it.
    pytest.fail("write me")


@pytest.mark.skip(reason="todo_parser.parse_todo_file is not implemented yet — see #JIRA-10")
def test_tags_without_a_trailing_number_are_found(tmp_path):
    # TODO: trap 4, and the sneakiest one. Build a fixture containing
    # `- [ ] **#ML-LOG · An experiment log.** ...` and
    # `- [ ] **#ML-LOG-b · The canary...** ...` — both real tags in Stocks —
    # and assert both parse.
    #
    # `#[A-Z]+-\d+` matches neither. A parser using it returns 26 of 28 items
    # and looks completely healthy, which is why this needs its own test rather
    # than trusting a total count somewhere else to catch it.
    pytest.fail("write me")


@pytest.mark.skip(reason="todo_parser.parse_all is not implemented yet — see #JIRA-11")
def test_real_files_yield_the_expected_counts():
    # TODO: the integration check, against the actual repo files rather than a
    # fixture. As of writing: 13 tagged items in Hardware-Check, 15 in Stocks,
    # 28 total.
    #
    # This test WILL need updating as you add TODO items, and that is fine —
    # it is the only test here that touches real data, and its job is to catch
    # a parser that silently finds most of the input. Update the numbers when
    # they change; do not delete it because it went red.
    pytest.fail("write me")


@pytest.mark.skip(reason="todo_parser.parse_todo_file is not implemented yet — see #JIRA-10")
def test_captures_the_phase_heading_as_context(hardware_check_excerpt):
    # TODO, only if you decided to capture it (see "The output shape"):
    # #SYS-1 and #MEM-1 sit under "Phase 1 — C++ core"; #MEM-2 under
    # "Phase 2 — Refactor". Assert each item carries the right one.
    #
    # If you decided NOT to capture phases, delete this test and say so in the
    # README — but note that phase maps cleanly onto a Jira epic or label, and
    # backfilling it after thirty issues exist means editing thirty issues.
    pytest.fail("write me")
