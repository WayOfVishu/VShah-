"""
Vocabularies and encodings: the participant table -> arrays a model can eat.

# TODO (Phase 3 -- see docs/TODO.md #FEAT-2) -- the draft's encode_features(),
# rethought for networks
#
# The draft asked how to turn champion / role / "the set of items owned" into
# numeric columns for logistic regression and XGBoost: one-hot, multi-hot,
# ordinal. That question survives, because the logistic-regression floor still
# needs an answer. Networks add a second, different one, and this module owes
# both:
#
#   encode_multi_hot()  one wide float matrix -- for logistic regression and
#                       the reference MLP. The draft's question, unchanged.
#   encode_ids()        small integer arrays -- for nn.Embedding. An id is not
#                       a quantity: champion 17 is not "more" than champion 16,
#                       and an embedding table never treats it as one. The
#                       draft's worry about integer codes implying a false
#                       ordering does not apply here -- work out why before
#                       #DL-2, because it is the whole point of embeddings.
#
# Both read the same vocabularies, built once by build_vocabularies().
#
# Context from the draft, still true: champion has ~170 distinct values, role
# has 5, items ~200. That cardinality gap decides which encodings are even
# reasonable for the linear floor.
#
# Design questions:
#   1. Reserve two ids up front -- PAD_ID for padding (items is 0-6 long, and
#      a batch has to be a rectangle) and UNK_ID for "never seen this". Why
#      does a champion the vocabulary has never seen need an id at all? (A new
#      champion ships mid-season. A model that crashes on one is worse than a
#      model that shrugs.)
#   2. Fit the vocabularies on the TRAIN rows only. They carry no labels, so
#      this is not label leakage -- but a min-count cutoff ("drop items seen
#      fewer than 5 times") computed over every row lets the test set decide
#      the feature set. It is also the only way to exercise the UNK path before
#      production does it for you. cli.py already passes train rows only; keep
#      it that way.
#   3. Allies vs enemies in the multi-hot matrix: one block each, or a single
#      block with +1 for allies and -1 for enemies (the side encoding the demo
#      uses)? The second is half the width and bakes in a symmetry. Does that
#      symmetry hold once one of the "allies" is the focal participant?
#   4. The vocabularies are part of the model. Id 17 means whatever it meant at
#      training time, forever. cli.py saves them in the checkpoint next to the
#      weights; #REC-1 must load them from there and never rebuild them from
#      new data. Keep them plain dicts of str/int -- torch.load(weights_only=True)
#      refuses anything else, on purpose.
#   5. gold_diff_at_snapshot is in the thousands and everything else is 0 or 1.
#      Scale it here (with train-row statistics, for question 2's reason) or
#      inside the model? Unscaled, it either swamps the first layer or gets
#      ignored, depending on initialisation.
#
# Research terms: "one-hot encoding", "multi-hot encoding", "entity embeddings
# of categorical variables".
#
# Contract cli.py relies on (keep it, or change cli.py with it):
#
#   build_vocabularies(train_rows) -> {"champion": {"<pad>": 0, "<unk>": 1, "Ahri": 2, ...},
#                                      "role": {...}, "item": {...}}
#       so len(vocabs["champion"]) is the embedding table size.
#   encode_ids(table, vocabs) -> {"champion": (N,), "role": (N,), "enemy_laner": (N,),
#                                 "allies": (N, 4), "enemies": (N, 5),
#                                 "items": (N, 6) padded with PAD_ID,
#                                 "gold_diff": (N,) float32, "y": (N,) float32}
#   encode_multi_hot(table, vocabs) -> (N, D) float32
"""

import numpy as np
import pandas as pd

PAD_ID = 0
UNK_ID = 1


def build_vocabularies(train_rows: pd.DataFrame) -> dict[str, dict]:
    """Token -> id mappings for champion, role and item, fitted on train rows."""
    raise NotImplementedError("build_vocabularies() is not implemented yet -- see docs/TODO.md #FEAT-2")


def encode_ids(table: pd.DataFrame, vocabs: dict[str, dict]) -> dict[str, np.ndarray]:
    """Integer id arrays for the embedding models, plus gold_diff and y."""
    raise NotImplementedError("encode_ids() is not implemented yet -- see docs/TODO.md #FEAT-2")


def encode_multi_hot(table: pd.DataFrame, vocabs: dict[str, dict]) -> np.ndarray:
    """One dense float matrix for logistic regression and the reference MLP."""
    raise NotImplementedError("encode_multi_hot() is not implemented yet -- see docs/TODO.md #FEAT-2")
