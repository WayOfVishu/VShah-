"""
The floor: majority class and logistic regression. **Built for you.**

In the draft these were #MOD-1, and yours to write. v3 moves them the other
way from everything else: with the networks now the point of the project,
the floor is evaluation infrastructure -- the yardstick every network is held
against (#EVAL-3) -- and you have already fit sklearn classifiers in the
Group20 notebook that Stocks' pipeline.py is modelled on. The new learning is
in leagueml/models/, not here.

The draft's framing still holds, from project-charter.md Section 13: "Start
with the simplest possible baseline (majority-class, then logistic regression)
... so you always have a floor to compare against." A network that does not
clearly beat logistic regression on held-out matches is not earning its
complexity, and saying so in the README is a result, not a failure.

The draft's two questions, which are still yours to answer in the README:
  - What ROC-AUC does the majority baseline get, and why? (Think about what
    ROC-AUC measures -- ranking -- before assuming the answer is 0 or 1.)
  - Does logistic regression need feature scaling here? On +/-1/0 one-hot
    columns, everything is already on one scale. That stops being true the
    moment gold_diff_at_snapshot (thousands) joins the matrix -- and then it
    matters for the networks too (#FEAT-2 question 5).

Logistic regression is also the smallest possible neural network: one
nn.Linear(n_features, 1) trained with BCEWithLogitsLoss, and weight_decay
playing the part of sklearn's L2 penalty. #DL-1 asks you to build exactly that
and check it matches this one -- the cleanest test of the training loop there is.
"""

import numpy as np
from sklearn.linear_model import LogisticRegression


def majority_class_baseline(y_train: np.ndarray, n: int) -> np.ndarray:
    """A constant predicted win-probability -- the training win rate -- for n rows.
    Uses no features at all."""
    return np.full(n, float(np.mean(y_train)))


def train_logistic_regression(X_train: np.ndarray, y_train: np.ndarray, *, C: float = 1.0) -> LogisticRegression:
    """Fit sklearn's L2-regularised logistic regression. C is the inverse
    penalty strength -- smaller C, simpler model."""
    return LogisticRegression(C=C, max_iter=2000).fit(X_train, y_train)
