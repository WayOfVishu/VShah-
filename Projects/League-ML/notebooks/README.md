# notebooks/

Deliberately empty. Once `#ING-4` has pulled some real matches and
`#FEAT-3` produces a participant table, add your own EDA notebook(s) here —
what does the win-rate distribution look like per champion/role, how many
matches ended in a remake, how sparse are the item columns at the 10-minute
mark, etc. (`#LML-4`)

Two things worth a notebook that are specific to the networks, and that the
terminal cannot show you:

- **Training curves.** `train_model()` returns a `TrainHistory` with
  `train_loss` and `val_loss` per epoch. Plot both. The gap between them is
  the single most useful picture in `#DL-3` and `#DL-4`.
- **The embeddings.** Once `#DL-2` works, the champion embedding table is a
  `(n_champions, dim)` matrix. Nearest neighbours, or a 2-D projection — do
  champions that play alike end up close? (`#DL-8`)

Not scaffolded on purpose: picking what's worth looking at in data you
actually collected is its own skill, and it's one no TODO comment can do
for you.
