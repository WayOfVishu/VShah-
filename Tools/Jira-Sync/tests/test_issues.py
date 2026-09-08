"""
Scaffolded tests for jira_sync.issues — skipped until #JIRA-6..9 land.

`to_adf` is the one function in this whole tool with a single, fully-specified
correct answer, and no network. Write its tests first and write them before the
implementation — this is the cheapest possible place to practise that, and the
ADF shape is exactly the kind of nested structure where a test tells you
immediately whether you nested it right.
"""

import pytest

from jira_sync import issues


# --- #JIRA-6: ADF -----------------------------------------------------------

@pytest.mark.skip(reason="issues.to_adf is not implemented yet — see #JIRA-6")
def test_to_adf_produces_the_documented_shape():
    # TODO: assert to_adf("hello") equals exactly:
    #
    #   {"type": "doc", "version": 1, "content": [
    #       {"type": "paragraph", "content": [
    #           {"type": "text", "text": "hello"}]}]}
    #
    # Assert the whole structure with one ==, not field by field. This is a
    # fixed contract Atlassian defined, not a design of yours, so there is no
    # reason to be lenient about it — and a partial assertion would pass on a
    # document missing "version", which Jira rejects.
    pytest.fail("write me")


@pytest.mark.skip(reason="issues.to_adf is not implemented yet — see #JIRA-6")
def test_to_adf_never_returns_a_bare_string():
    # TODO: assert isinstance(to_adf("x"), dict).
    #
    # Trivial, and it is the guard against the failure mode described at the
    # top of issues.py: a plain string does not error, it saves an EMPTY
    # description. The issue gets created, your script prints success, and the
    # description is blank until you happen to open the board.
    #
    # A test this cheap for a failure this silent is worth having.
    pytest.fail("write me")


@pytest.mark.skip(reason="issues.to_adf is not implemented yet — see #JIRA-6")
def test_to_adf_handles_empty_and_multiline_text():
    # TODO: what does to_adf("") produce — a doc with an empty paragraph, or a
    # doc with no content? What about text with "\n\n" in it, which your TODO
    # bodies definitely contain?
    #
    # ADF represents paragraphs structurally, so a two-paragraph string
    # arguably wants two paragraph nodes rather than one containing a newline.
    # Decide, and note that "one paragraph with newlines in it" renders as a
    # single run-on block in Jira — which may be fine for v1 and is worth
    # knowing you chose.
    pytest.fail("write me")


# --- #JIRA-7: create ---------------------------------------------------------

@pytest.mark.skip(reason="issues.create_issue is not implemented yet — see #JIRA-7")
def test_create_issue_nests_fields_correctly(monkeypatch):
    # TODO: patch client.request with a recorder and assert the body sent has
    # everything under "fields", the project key as {"key": ...}, and the
    # issuetype as {"name": ...} — not bare strings.
    #
    # Also assert the shape asymmetry that catches everyone: `summary` is a
    # plain string while `description` is an ADF dict, in the same object.
    pytest.fail("write me")


@pytest.mark.skip(reason="issues.create_issue is not implemented yet — see #JIRA-7")
def test_create_issue_sends_adf_not_a_string(monkeypatch):
    # TODO: the guard against the silent failure, at the level that matters.
    # Assert the description in the outgoing body is a dict with
    # type == "doc", regardless of what was passed in.
    #
    # test_to_adf_never_returns_a_bare_string checks the helper; this checks
    # that create_issue actually *called* it. Both can be true independently,
    # and only this one catches "I wrote to_adf and forgot to use it".
    pytest.fail("write me")


# --- #JIRA-8/9: idempotency --------------------------------------------------

@pytest.mark.skip(reason="issues.sync_todos is not implemented yet — see #JIRA-9")
def test_sync_is_idempotent(monkeypatch):
    # TODO: the test that justifies the whole idempotency design discussion in
    # issues.py. Run sync_todos twice against a fake where the first run
    # creates issues and the second finds them existing. Assert the second run
    # creates NOTHING.
    #
    # Whichever matching strategy you chose — tag in summary, label, local
    # state file — this test is the same, which is the useful property: it
    # tests the behaviour, not the mechanism, so it survives you changing your
    # mind about the mechanism.
    pytest.fail("write me")


@pytest.mark.skip(reason="issues.sync_todos is not implemented yet — see #JIRA-9")
def test_reworded_todo_does_not_create_a_duplicate(monkeypatch):
    # TODO: the test that separates a real matching strategy from a naive one.
    # Sync, then change the item's *description text* while keeping its tag,
    # then sync again. Assert nothing new was created.
    #
    # A strategy matching on summary text fails here. That is the point — this
    # test is how you find out that "search by summary" was the wrong choice,
    # in a second, rather than after your board has two #MEM-T1s on it.
    pytest.fail("write me")


@pytest.mark.skip(reason="issues.sync_todos is not implemented yet — see #JIRA-9")
def test_dry_run_creates_nothing(monkeypatch):
    # TODO: assert that with dry_run=True (the default — see #JIRA-9), no
    # write request is issued at all, while the returned report still describes
    # what would have happened.
    #
    # Assert on the transport, not the report. A dry run that builds a correct
    # report and also POSTs is exactly the bug this test exists for, and the
    # report looks identical either way.
    pytest.fail("write me")
