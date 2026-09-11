"""
The reference network -- **built for you**. A small feed-forward net over one
dense feature vector.

Carried over from the draft's WinPredictorNN with one change: forward() takes
the batch dict and reads batch["x"], so it trains through the same loop as
every other model. Read it next to train.py; together they are the complete
worked example, and everything in #DL-2 onwards is a variation on them.

Expect it to roughly *tie* logistic regression on flat one-hot features, and
don't read that as a bug. Over one-hot inputs, all the hidden layers add
beyond logistic regression is interactions between columns, and a few
thousand matches rarely carry enough of them to learn. The synthetic world
plants some (same-team synergy pairs), so it is the one place a gap might
show -- #EVAL-3 is how you find out whether a gap is real. That this model
ties the floor is the draft's Section 10 argument about tabular data,
confirmed rather than contradicted; the networks that get a real chance to
beat it are the ones that change the input's shape (#DL-2, #DL-5, #DL-7).
"""

import torch
from torch import nn


class WinPredictorNN(nn.Module):
    """Two hidden layers with ReLU and one logit out. Deliberately shallow --
    thousands of rows and tens to low hundreds of columns do not call for
    depth."""

    def __init__(self, n_features: int, hidden_dim: int = 32) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        # Raw logits out -- BCEWithLogitsLoss (train.py) applies the sigmoid
        # internally, which is numerically more stable than doing sigmoid()
        # here and using plain BCELoss.
        return self.net(batch["x"]).squeeze(-1)


def build(n_features: int, hidden_dim: int = 32, **_) -> WinPredictorNN:
    return WinPredictorNN(n_features=n_features, hidden_dim=hidden_dim)
