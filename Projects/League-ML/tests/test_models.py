"""Shape and sanity tests for the networks.

The overfit-a-tiny-batch test is the first thing to write for any new model
(#DL-1). A network with far more parameters than examples should memorise 32
random labels almost perfectly. If it cannot, the bug is in the model or the
loop -- a detached tensor, a missing zero_grad, a wrong loss -- and no amount
of data or tuning will help. It costs a second to run and catches most of
what goes wrong in a first PyTorch model.
"""

import pytest
import torch
from torch import nn

from leagueml.models import build_model


def _overfit(model: nn.Module, batch: dict, steps: int = 300) -> float:
    torch.manual_seed(0)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
    loss_fn = nn.BCEWithLogitsLoss()
    for _ in range(steps):
        optimizer.zero_grad()
        loss = loss_fn(model(batch), batch["y"])
        loss.backward()
        optimizer.step()
    return loss.item()


def test_mlp_returns_one_logit_per_row():
    model = build_model("mlp", n_features=12)
    assert model({"x": torch.zeros(7, 12)}).shape == (7,)


def test_mlp_can_overfit_a_tiny_batch():
    torch.manual_seed(0)
    batch = {"x": torch.randn(32, 12), "y": (torch.rand(32) > 0.5).float()}
    assert _overfit(build_model("mlp", n_features=12), batch) < 0.05


@pytest.mark.skip(reason="EmbeddingModel is not implemented yet -- see docs/TODO.md #DL-2")
def test_embedding_model_can_overfit_a_tiny_batch():
    # TODO: the same test as the MLP's, on a batch shaped like encode_ids()
    # output. Write it before the model works -- it is how you will know when
    # it does.
    pytest.fail("write me")


@pytest.mark.skip(reason="CompositionModel is not implemented yet -- see docs/TODO.md #DL-5")
def test_shuffling_the_allies_does_not_move_the_prediction():
    # TODO: composition.py design question 1. Permute the (B, 4) allies
    # columns and assert the logits are unchanged (torch.allclose). If they
    # move, a positional signal has crept in.
    pytest.fail("write me")


@pytest.mark.skip(reason="CompositionModel is not implemented yet -- see docs/TODO.md #DL-5")
def test_swapping_the_teams_flips_the_probability():
    # TODO: composition.py design question 2 -- only if you built the
    # antisymmetry in. P(win | A vs B) + P(win | B vs A) == 1, to float
    # tolerance. If you chose data augmentation instead, this test tells you
    # how close "approximately" actually got.
    pytest.fail("write me")


@pytest.mark.skip(reason="TimelineModel is not implemented yet -- see docs/TODO.md #DL-7")
def test_timeline_model_returns_one_logit_per_match():
    # TODO: frames of shape (B, T, F) in, (B,) out -- and the overfit test.
    pytest.fail("write me")
