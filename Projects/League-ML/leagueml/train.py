"""
The training loop -- **built for you**, and the one piece of deep-learning
code here you are meant to read before writing any of your own.

Carried over from the draft's torch_model.py (v2 built it because the
deep-learning baseline was "None" -- exposure before derivation), generalised
so every model in leagueml/models/ trains through the same loop: batches are
dicts of tensors, each model reads the keys it needs, and the loop only ever
touches batch["y"].

The five lines that are the whole of supervised deep learning are in
`_train_one_epoch`:

    optimizer.zero_grad()           # forget the previous batch's gradients
    logits = model(batch)           # forward pass
    loss = loss_fn(logits, y)       # how wrong, as one number
    loss.backward()                 # d(loss)/d(parameter), for every parameter
    optimizer.step()                # move each parameter a little downhill

#DL-1 asks you to break each of those on purpose and watch what happens. Do
that before #DL-2. You will be debugging this loop from the other side for the
rest of the project, and a symptom is far easier to recognise when you have
caused it deliberately once.

Two things worth noticing that are easy to read past:

- `model.train()` / `model.eval()` switch layers that behave differently at
  training time -- dropout (#DL-4) and batch norm. The reference MLP has
  neither, so forgetting eval() does nothing to it yet. It will matter the day
  you add dropout, which is exactly when you will have forgotten this.
- `@torch.no_grad()` on the evaluation functions stops PyTorch recording the
  operations it would need for a backward pass that is never coming. Without
  it, evaluation still works; it is just slower and holds more memory.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from leagueml.config import SEED


@dataclass
class TrainConfig:
    epochs: int = 30
    lr: float = 1e-3
    batch_size: int = 64
    weight_decay: float = 0.0   # an L2 penalty, applied by the optimizer -- #DL-4
    device: str = "cpu"
    seed: int = SEED
    log_every: int = 10


@dataclass
class TrainHistory:
    """Mean loss per epoch. Plot both curves -- the gap between them is the
    single most useful picture in this project (#DL-3, #DL-4)."""

    train_loss: list[float] = field(default_factory=list)
    val_loss: list[float] = field(default_factory=list)

    @property
    def best_epoch(self) -> int:
        """1-based epoch with the lowest validation loss."""
        return int(np.argmin(self.val_loss)) + 1 if self.val_loss else 0


def set_seed(seed: int) -> None:
    """Seed Python, NumPy and PyTorch together, so a run can be repeated."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def _to_device(batch: dict[str, torch.Tensor], device: str) -> dict[str, torch.Tensor]:
    return {name: t.to(device) for name, t in batch.items()}


def _train_one_epoch(model: nn.Module, loader: DataLoader, loss_fn: nn.Module,
                     optimizer: torch.optim.Optimizer, device: str) -> float:
    model.train()
    total, seen = 0.0, 0
    for batch in loader:
        batch = _to_device(batch, device)
        optimizer.zero_grad()
        logits = model(batch)
        loss = loss_fn(logits, batch["y"])
        loss.backward()
        # (#DL-7) Recurrent models are where exploding gradients actually show
        # up. torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm) goes
        # here, between backward() and step() -- nowhere else works.
        optimizer.step()
        total += loss.item() * len(batch["y"])
        seen += len(batch["y"])
    return total / seen


@torch.no_grad()
def _mean_loss(model: nn.Module, loader: DataLoader, loss_fn: nn.Module, device: str) -> float:
    model.eval()
    total, seen = 0.0, 0
    for batch in loader:
        batch = _to_device(batch, device)
        total += loss_fn(model(batch), batch["y"]).item() * len(batch["y"])
        seen += len(batch["y"])
    return total / seen


def train_model(model: nn.Module, train_ds: Dataset, val_ds: Dataset,
                cfg: TrainConfig | None = None, *,
                log: Callable[[str], None] | None = print) -> TrainHistory:
    """Mini-batch training with Adam and binary cross-entropy, printing train and
    validation loss as it goes so you can watch it learn -- or not.

    The model's initial weights were drawn when it was built, before this
    runs. For a repeatable run, call set_seed() before building the model too
    -- cli.py does.
    """
    cfg = cfg or TrainConfig()
    set_seed(cfg.seed)  # dropout masks and anything else drawn during training
    model.to(cfg.device)

    # BCEWithLogitsLoss takes raw logits and applies the sigmoid itself, which is
    # numerically more stable than sigmoid() in the model plus plain BCELoss.
    loss_fn = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)

    # A seeded generator makes the shuffle order part of the seed, so two runs
    # with the same TrainConfig see the same batches in the same order.
    shuffle_order = torch.Generator().manual_seed(cfg.seed)
    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True,
                              generator=shuffle_order)
    val_loader = DataLoader(val_ds, batch_size=max(cfg.batch_size, 512))

    history = TrainHistory()
    for epoch in range(1, cfg.epochs + 1):
        history.train_loss.append(_train_one_epoch(model, train_loader, loss_fn, optimizer, cfg.device))
        history.val_loss.append(_mean_loss(model, val_loader, loss_fn, cfg.device))

        if log and (epoch == 1 or epoch % cfg.log_every == 0 or epoch == cfg.epochs):
            log(f"  epoch {epoch:3d}/{cfg.epochs}  train_loss={history.train_loss[-1]:.4f}"
                f"  val_loss={history.val_loss[-1]:.4f}")

        # TODO #DL-3 -- early stopping, and keeping the best weights.
        #
        # As written, this runs every epoch no matter what val_loss does, and
        # the model you get back holds the weights from the *last* epoch. Once a
        # network starts overfitting -- train_loss still falling, val_loss
        # turning back up -- those are not the weights you want.
        #
        # Design questions:
        #   1. "Patience": how many epochs without a new best val_loss before
        #      stopping? Too small and noise stops you early; too large and
        #      you are training an overfit model for nothing.
        #   2. Where do the best weights live while training continues? A
        #      reference to model.state_dict() is NOT a copy -- the tensors in
        #      it keep changing underneath you. (This one bites everyone once.)
        #   3. Should "best" be the lowest val_loss, or the highest val AUC?
        #      They disagree more often than you'd expect, and the recommender
        #      cares about calibrated probabilities (#DL-6), which is a hint.

    return history


@torch.no_grad()
def predict_proba(model: nn.Module, ds: Dataset, *, batch_size: int = 1024,
                  device: str = "cpu") -> np.ndarray:
    """Win probabilities (sigmoid of the logits) for every row of `ds`, in order --
    the same shape as sklearn's predict_proba(...)[:, 1]."""
    model.eval()
    model.to(device)
    out = []
    for batch in DataLoader(ds, batch_size=batch_size):
        out.append(torch.sigmoid(model(_to_device(batch, device))).cpu())
    return torch.cat(out).numpy()


def save_checkpoint(path: Path, model: nn.Module, **extra) -> None:
    """Weights plus whatever is needed to rebuild and use the model -- the model
    name, its constructor dims, and above all #FEAT-2's vocabularies. Keep
    `extra` to plain dicts, lists, strings and numbers: load_checkpoint uses
    torch.load(weights_only=True), which refuses anything else on purpose,
    because a full pickle can execute code when it is loaded."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), **extra}, path)


def load_checkpoint(path: Path) -> dict:
    """The dict save_checkpoint wrote. Rebuild the model from its name and dims,
    then model.load_state_dict(checkpoint["state_dict"])."""
    return torch.load(Path(path), map_location="cpu", weights_only=True)
