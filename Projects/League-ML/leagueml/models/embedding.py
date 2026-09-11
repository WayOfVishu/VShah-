"""
Learned embeddings for champions, roles and items -- the first model in this
project that is deep learning for a reason rather than for the résumé.

# TODO (Phase 4 -- see docs/TODO.md #DL-2)
#
# The reference MLP eats a one-hot/multi-hot vector: ~170 champion columns
# with a handful non-zero. That works, but it treats every champion as
# unrelated to every other -- two assassins are exactly as different as an
# assassin and a tank, and anything learned about one teaches nothing about
# the other. An embedding gives each id a small learned vector instead.
# Champions that affect games alike can end up close together, and what the
# model learns about one partly transfers to its neighbours. It is word2vec's
# idea, applied to champions and items instead of words -- and the most
# convincing picture this project can produce, if it works (#DL-8).
#
# Inputs this model reads (produced by #FEAT-2's encode_ids()):
#   champion (B,)  role (B,)  enemy_laner (B,)  allies (B, 4)  enemies (B, 5)
#   items (B, 6) padded with PAD_ID  gold_diff (B,) float  -- and y, which it ignores
#
# Design questions:
#   1. Embedding width. 8? 16? 32? There is a rule of thumb that ties width to
#      the fourth root of the vocabulary size -- find where you read it, ask
#      whether it applies to ~170 champions, then treat width as a
#      hyperparameter and log it (#EVAL-1).
#   2. Items are a *set* of 0-6 ids. nn.EmbeddingBag pools a bag in one call
#      (mode="mean" or "sum"); nn.Embedding(padding_idx=PAD_ID) plus your own
#      pooling does the same by hand. Mean or sum -- which one can tell "two
#      items" from "one item", and is that information you want, given that
#      gold_diff already says who is ahead? (#REC-1's confounding trap lives
#      exactly here.)
#   3. One champion table shared by the focal champion, the allies and the
#      enemies -- or separate tables? Shared means "Zed" is one vector
#      wherever he sits. Then how does the model know *where* he sits? (Adding
#      a learned side embedding to the champion embedding is the transformer
#      answer, and the bridge to #DL-5.)
#   4. The four allies: pool them (order-free) or concatenate four slots? If
#      you concatenate, the model has to learn the same thing four times, and
#      "ally slot 2" means nothing. Pooling is the Deep Sets idea: a function
#      of a set should not care about the order you listed it in.
#   5. How will you know it learned anything the MLP didn't? Synthetic data
#      with synergy > 0 is the controlled test, because you planted the
#      answer. #EVAL-3 is the comparison; tests/test_models.py has the
#      overfit-a-tiny-batch test waiting for this class.
"""

import torch
from torch import nn


class EmbeddingModel(nn.Module):
    """Champion, role and item embeddings, pooled and passed through a small MLP."""

    def __init__(self, n_champions: int, n_roles: int, n_items: int, dim: int = 16) -> None:
        super().__init__()
        raise NotImplementedError("EmbeddingModel is not implemented yet -- see docs/TODO.md #DL-2")

    def forward(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        raise NotImplementedError("see docs/TODO.md #DL-2")


def build(n_champions: int, n_roles: int, n_items: int, dim: int = 16, **_) -> EmbeddingModel:
    return EmbeddingModel(n_champions=n_champions, n_roles=n_roles, n_items=n_items, dim=dim)
