"""
Tensor plumbing between NumPy arrays and the training loop. **Built for you.**

Every model in leagueml/models/ reads its inputs *by name* from a dict of
tensors -- the MLP reads batch["x"], the embedding model reads
batch["champion"], batch["items"] and so on, and the training loop only ever
touches batch["y"]. This module is what turns a dict of equal-length arrays
into that. PyTorch's default collate function already stacks dicts of tensors
key by key, so no custom collate is needed while every input is a fixed-width
rectangle -- which, with items padded to 6 slots and a fixed frame count, all
of this project's inputs are.
"""

from __future__ import annotations

import numpy as np
import torch
from torch.utils.data import Dataset


def _as_tensor(name: str, values) -> torch.Tensor:
    array = np.asarray(values)
    # The label is always float: BCEWithLogitsLoss wants float targets, and an
    # integer y fails with a dtype error far away from where it was made.
    if name == "y":
        return torch.from_numpy(array.astype(np.float32))
    # Integer arrays are ids for nn.Embedding, which requires int64 ("long").
    if np.issubdtype(array.dtype, np.integer):
        return torch.from_numpy(array.astype(np.int64))
    return torch.from_numpy(array.astype(np.float32))


class DictDataset(Dataset):
    """Rows of several equal-length arrays, served as a dict of tensors.

        ds = DictDataset(x=X, y=y)              # the MLP
        ds = DictDataset(**encode_ids(...))     # the embedding models (#FEAT-2)
        ds[0] -> {"x": tensor([...]), "y": tensor(1.)}
    """

    def __init__(self, **arrays) -> None:
        if "y" not in arrays:
            raise ValueError("a DictDataset needs a 'y' array -- the training loop reads it")
        lengths = {name: len(values) for name, values in arrays.items()}
        if len(set(lengths.values())) != 1:
            raise ValueError(f"arrays differ in length: {lengths}")
        self.tensors = {name: _as_tensor(name, values) for name, values in arrays.items()}
        self._n = next(iter(lengths.values()))

    def __len__(self) -> int:
        return self._n

    def __getitem__(self, i: int) -> dict[str, torch.Tensor]:
        return {name: t[i] for name, t in self.tensors.items()}

    def subset(self, indices) -> "DictDataset":
        """The rows at `indices` -- how the train/val/test splits are applied."""
        idx = torch.as_tensor(np.asarray(indices), dtype=torch.long)
        out = DictDataset.__new__(DictDataset)
        out.tensors = {name: t[idx] for name, t in self.tensors.items()}
        out._n = len(idx)
        return out
