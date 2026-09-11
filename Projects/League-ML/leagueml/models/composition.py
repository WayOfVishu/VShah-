"""
Attention over the ten champions -- synergy and counters as interactions a
network has to discover.

# TODO (Phase 4 -- see docs/TODO.md #DL-5)
#
# #DL-2 pools teammates into one vector, which by construction cannot see
# *which* champions are together -- a set's mean forgets pairs. Synergy (these
# two on one team) and counters (this one against that one) are exactly pairs.
# Self-attention is the standard tool for "every element looks at every other":
# treat each champion as a token, let a small nn.TransformerEncoder mix them,
# pool, and read a logit off the top.
#
# A token = champion embedding + side embedding (ally / enemy) + role
# embedding, summed. The focal participant's items can join as extra tokens
# or be pooled onto the focal champion's token -- your call, and worth a
# sentence in the README.
#
# Inputs: the same encode_ids() arrays #DL-2 reads.
#
# Design questions:
#   1. Why no positional encoding? A transformer over text needs one because
#      word order matters. Here it mostly doesn't: five champions listed in a
#      different order are the same team. Attention without positions is
#      permutation-equivariant, and pooling makes it invariant -- the
#      symmetry you want, for free. What *does* matter (side, role) goes in as
#      embeddings instead. tests/test_models.py has a test waiting that
#      shuffles the allies and asserts the output does not move.
#   2. A second symmetry you can enforce rather than hope for: swap the two
#      teams and P(win) must become 1 - P(win). A plain model will only
#      approximately learn that. Options: (a) train on side-swapped copies of
#      every row, or (b) build it in -- logit = f(A, B) - f(B, A) is exactly
#      antisymmetric. Which is cheaper, and which is exact? (There is a test
#      waiting for this one too.)
#   3. Size. d_model, heads, layers: on a few thousand matches, even one layer
#      of d_model=32 can memorise the training set. What is your evidence it
#      hasn't -- the #DL-3 / #DL-4 curves, and #EVAL-4's learning curve?
#   4. Attention weights are tempting to read as "which champion mattered".
#      Look up why that interpretation is contested before an attention
#      heatmap goes in the README.
"""

import torch
from torch import nn


class CompositionModel(nn.Module):
    """Transformer encoder over champion tokens (+ the focal player's items)."""

    def __init__(self, n_champions: int, n_roles: int, n_items: int, d_model: int = 32,
                 n_heads: int = 4, n_layers: int = 1) -> None:
        super().__init__()
        raise NotImplementedError("CompositionModel is not implemented yet -- see docs/TODO.md #DL-5")

    def forward(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        raise NotImplementedError("see docs/TODO.md #DL-5")


def build(n_champions: int, n_roles: int, n_items: int, d_model: int = 32, n_heads: int = 4,
          n_layers: int = 1, **_) -> CompositionModel:
    return CompositionModel(n_champions, n_roles, n_items, d_model=d_model,
                            n_heads=n_heads, n_layers=n_layers)
