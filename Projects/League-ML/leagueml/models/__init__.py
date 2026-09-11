"""Model registry -- `py run.py train --model <name>` looks names up here.

    mlp          built    the reference network over one dense vector
    embedding    #DL-2    learned champion / role / item embeddings
    composition  #DL-5    attention over the ten champions
    timeline     #DL-7    a recurrent model over per-minute frames

Every module exposes `build(**dims) -> nn.Module`, and every model's
forward() takes the batch dict and returns one logit per row. The floor
(majority class, logistic regression) is not in here -- it is sklearn, and it
lives in baselines.py.
"""

from importlib import import_module

from torch import nn

MODELS = {
    "mlp": "leagueml.models.mlp",
    "embedding": "leagueml.models.embedding",
    "composition": "leagueml.models.composition",
    "timeline": "leagueml.models.timeline",
}


def build_model(name: str, **dims) -> nn.Module:
    if name not in MODELS:
        raise ValueError(f"unknown model {name!r}; choose from {', '.join(MODELS)}")
    return import_module(MODELS[name]).build(**dims)
