"""
A sequence model over the timeline: who is winning, minute by minute.

# TODO (Phase 6 -- see docs/TODO.md #DL-7)
#
# A different question from the rest of the project, on purpose. The other
# models ask "does this draft and these items win?"; this one asks "given how
# the first N minutes went, who wins?" -- the win-probability line a broadcast
# shows. It is the natural home for a recurrent network, and the closest
# thing here to Stocks' #ML-11 (a sequence model over daily bars), so doing
# either one first makes the other easier.
#
# Inputs:
#   frames (B, T, F) float -- per-minute features for the focal team vs the
#       other: gold difference at minimum; xp, level and creep-score
#       differences are the obvious next columns. From #FEAT-4's
#       participant_frames on real data; synthetic matches carry a
#       gold-difference curve already (`py run.py train --model timeline`
#       wires it up as F=1).
#
# Design questions:
#   1. GRU, LSTM, or a 1-D temporal convolution? Start with nn.GRU(hidden=32,
#      one layer, batch_first=True) -- fewer moving parts than an LSTM, and
#      rarely worse at this length.
#   2. Scale. Gold differences are in the thousands, and a recurrent net fed
#      raw thousands saturates its gates on the first step. Normalise -- with
#      statistics from the train split only (the same reason #FEAT-2 fits its
#      vocabularies on train rows).
#   3. Predict once, at the end, or at every minute? Emitting a logit per step
#      and averaging the loss over steps turns one training example into T of
#      them and produces the whole win-probability curve. The every-minute
#      version is the interesting one.
#   4. A leak specific to timelines: game length. A sequence that stops at
#      minute 16 says someone surrendered. Check the earliest surrender on
#      your patch against FRAME_MINUTES, and make sure a short game cannot
#      announce its own ending through padding.
#   5. The floor here is strong: logistic regression on the gold difference at
#      the last frame alone. Whoever is ahead in gold at minute 15 usually
#      wins. A GRU that cannot beat that is not reading the *shape* of the
#      curve, only its last value -- and that is worth knowing either way.
#   6. Exploding gradients are a recurrent-network problem in particular; see
#      the clip_grad_norm_ note in train.py.
"""

import torch
from torch import nn


class TimelineModel(nn.Module):
    """GRU over per-minute frames, one logit out."""

    def __init__(self, n_frame_features: int, hidden_dim: int = 32) -> None:
        super().__init__()
        raise NotImplementedError("TimelineModel is not implemented yet -- see docs/TODO.md #DL-7")

    def forward(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        raise NotImplementedError("see docs/TODO.md #DL-7")


def build(n_frame_features: int, hidden_dim: int = 32, **_) -> TimelineModel:
    return TimelineModel(n_frame_features=n_frame_features, hidden_dim=hidden_dim)
