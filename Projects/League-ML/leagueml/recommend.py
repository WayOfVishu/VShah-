"""
Item recommendations: given your champion, your role and your lane opponent,
rank candidate items by predicted win-probability lift.

    py run.py recommend --champion Ahri --enemy Zed --role MIDDLE

# TODO (Phase 5 -- see docs/TODO.md #REC-1) -- the draft's #MOD-4, now
# against a network
#
# The deliverable, Functional Requirement in project-charter.md Section 8:
#     "Inference must return top-3 items ranked by predicted win-probability
#     lift, given champion + matchup context"
#
# From the draft, still the first decision -- "win-probability lift" needs a
# baseline to lift *against*. Some options, roughly increasing in complexity:
#   (a) lift over the majority-class baseline probability
#   (b) lift over this exact champion+role+enemy combo's average win rate
#       with no specific item assumption
#   (c) lift over the single most common item choice for that matchup
# Any of these is defensible for an MVP -- pick one and say why in your
# README, don't silently default to whichever was easiest to code.
#
# Also from the draft: where do "candidate items" come from -- every item in
# items_static? Only ones seen for this champion and role in training? That is
# a scope decision worth making deliberately (and #FEAT-1's decision about
# components and consumables has already made half of it).
#
# (v3) Four things a network makes you decide that the draft's version hid:
#
#   1. Confounding -- the big one. Items at minute 10 are not handed out at
#      random: a player who is already ahead has more gold and buys more, and
#      pricier, items. A model trained on "items owned at 10 -> win" learns that
#      rich inventories win, and a recommender built on it tells everyone to be
#      richer. The synthetic generator plants exactly this (item count follows
#      the gold lead), so you can watch it happen before real data exists.
#      Ways to fight it, in rough order of rigour:
#        - hold gold_diff_at_snapshot fixed when you swap candidate items in --
#          it is in the participant table for this reason
#        - compare items at equal cost (items_static.gold_total): "which
#          1,300-gold item" rather than "which items"
#        - say what it is: this is observational data, and the ranking means
#          "associated with winning, holding gold fixed", not "causes
#          winning". That sentence in the README is worth more in an
#          interview than the ranking itself.
#   2. The rest of the draft. The CLI gets champion, enemy and role; the
#      model was trained on four allies and four more enemies too. What goes
#      in those slots? (a) an unknown token -- only meaningful if the model saw
#      unknowns in training (look up "token dropout"); (b) average over real
#      teams from your data that contain this matchup; (c) optional CLI
#      arguments. (b) is the principled one, (a) the quick one.
#   3. The vocabulary. Use the one saved in the checkpoint (#FEAT-2 question
#      4), never one rebuilt from new data. A candidate the training vocabulary
#      has never seen encodes as UNK -- recommending "<unk>" is a bug in the
#      candidate list, not a recommendation.
#   4. Mechanics: one forward pass, not one per item. Build the context once,
#      stack one row per candidate, run a single batch through the model under
#      torch.no_grad(), subtract the baseline, sort.
"""


def recommend_items(champion: str, enemy: str, role: str, model, vocabs: dict | None,
                    *, top_k: int = 3) -> list[tuple[str, float]]:
    """Return the top_k (item_name, win_probability_lift) pairs for this matchup."""
    raise NotImplementedError("recommend_items() is not implemented yet -- see docs/TODO.md #REC-1")
