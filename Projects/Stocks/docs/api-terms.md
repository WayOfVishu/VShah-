# API Terms — audit

Checked against each provider's own published terms, September 2026. Every
source is linked; re-check before deploying anything public, because these
change (Reddit's terms changed twice between 2023 and 2025).

**Short answer: yes, everything is free at the volumes this project uses.** But
"free" is doing several different jobs in that sentence, and three of the six
have conditions that matter.

---

## Summary

| provider | free? | key | the catch |
|---|---|---|---|
| **GDELT** | Yes, genuinely | none | **Must cite GDELT and link the site** |
| **FRED** | Yes | free key | **Must display an exact disclaimer notice** |
| **yfinance / Yahoo** | Yes | none | **Yahoo's API is "personal use only"** |
| **Alpha Vantage** | Yes, 25 req/day | free key | commercial use not addressed in their terms |
| **NewsAPI** | Developer plan | free key | **Prohibited in production. Not used by default.** |
| **Reddit** | Yes, non-commercial | approval | self-serve signup closed; manual approval since late 2025 |

---

## The three that carry obligations

### GDELT — free, but attribution is required

The most permissive of the set, and the keystone of this project (it is the
only free source reaching back 12 months, so DS2 exists because of it).

> "All datasets released by the GDELT Project are available for unlimited and
> unrestricted use for any academic, commercial, or governmental use of any
> kind without fee."

No key, no quota, commercial use explicitly allowed. The one condition:

> "any use or redistribution of the data must include a citation to the GDELT
> Project and a link to this website."

**Where this is honoured:** the web app footer credits GDELT with a link, in
`frontend/index.html`. Do not remove it.

Note that "no published rate limit" is not "no rate limit" — GDELT starts
returning 429s below roughly one call per five seconds and keeps returning them
for minutes afterwards. That is an operational limit, not a licensing one, and
`GdeltProvider.MIN_INTERVAL` handles it.

Source: [gdeltproject.org/about.html](https://www.gdeltproject.org/about.html)

### FRED — free, but a specific notice is mandatory

Free with a free API key. The terms require this text, verbatim, displayed
prominently:

> "This product uses the FRED® API but is not endorsed or certified by the
> Federal Reserve Bank of St. Louis."

**Where this is honoured:** the web app footer, verbatim, in
`frontend/index.html`. It is a quotation from the licence — do not reword it.

Other terms worth knowing: the Bank reserves the right to impose or adjust
bandwidth and transaction limits at any time; you may not replicate the FRED
experience or use bandwidth that affects their server stability; and third-party
data within FRED may carry its own restrictions that you are responsible for.

Source: [fred.stlouisfed.org/docs/api/terms_of_use.html](https://fred.stlouisfed.org/docs/api/terms_of_use.html)

### yfinance / Yahoo — free, and the one to think hardest about

yfinance is Apache-licensed open source and free. But yfinance is not Yahoo,
and the constraint comes from Yahoo, not from yfinance:

> "yfinance is **not** affiliated, endorsed, or vetted by Yahoo, Inc. ...
> Remember - the Yahoo! finance API is intended for personal use only."

So: **fine for a personal project, which is what this is.** Not fine for a
public or commercial deployment, and no amount of caching or attribution fixes
that — it is a use-restriction, not an attribution requirement.

This is the single most important line in this document, because yfinance is
the default provider for DS1 *and* DS4, i.e. all the price data. If this ever
stops being a personal project, prices are the piece that has to be re-sourced
(a paid tier of Alpha Vantage, Tiingo, Polygon, or a broker's data feed) before
anything else.

**Where this is honoured:** the web app disclaimer states the app is a personal
research project and not a commercial service.

Sources: [github.com/ranaroussi/yfinance](https://github.com/ranaroussi/yfinance)

---

## The two that are simply limited

### Alpha Vantage — 25 requests/day

Free with a free key. Their pricing page states the free limit and does not
address commercial use either way, so treat commercial use as unresolved rather
than permitted.

25/day is why this is positioned as a *fallback* and never a sweep provider: it
is enough to serve the web app (one ticker, one request, cache absorbs repeats)
and nowhere near enough for a walk-forward panel build.

Source: [alphavantage.co/premium](https://www.alphavantage.co/premium/)

### Reddit — free for non-commercial, but hard to get now

Free at 100 queries/minute per OAuth client for non-commercial use — personal
projects, bots, moderator tools, academic research. This project qualifies.

Two practical problems:

1. **Self-service registration closed in late 2025.** Under Reddit's Responsible
   Builder Policy, every new OAuth client — free or paid — now goes through a
   manual approval ticket. You cannot just create an app and start.
2. Commercial access starts around **$12,000/month**.

Combined with the fact that Reddit's search API cannot filter by date range
(Pushshift, which solved this, closed in 2023), Reddit is the weakest link in
the design. It serves DS3 only, it is off unless you configure credentials, and
the project runs without it.

Sources: [socialcrawl.dev](https://www.socialcrawl.dev/blog/reddit-data-api-2026),
[prowlo.com](https://prowlo.com/blog/reddit-data-api)

---

## The one that is off by default

### NewsAPI — free plan cannot be used in production

This is the finding that changed the code. The Developer plan:

> "may be used for development and testing in a development environment only,
> and cannot be used in a staging or production environment (including
> internally)."

Plus 100 requests/day and one month of article history.

A hosted web app is a production environment. Using the free NewsAPI key to
serve it would breach their terms, and the one-month history means it cannot
build DS2 anyway.

**So NewsAPI is now opt-in rather than automatic.** Setting `NEWSAPI_API_KEY`
alone no longer enables it; `NEWSAPI_ALLOW_NONPRODUCTION=true` is also required,
and `NewsApiProvider.available()` checks both. The extra flag exists so that
enabling a development-only provider is a deliberate act with the reason
attached, rather than a side effect of pasting a key into `.env`.

Source: [newsapi.org/pricing](https://newsapi.org/pricing)

---

## What this means in practice

**As a personal research project run locally — which is what this is — every
provider is free and within terms.**

If it ever becomes something public, in order of urgency:

1. **Replace yfinance.** Personal-use-only is a hard blocker, and it supplies
   all price data.
2. **Keep NewsAPI off**, or buy a plan.
3. **Keep the GDELT and FRED notices** in the footer. They are licence terms,
   not politeness.
4. **Re-check Reddit** if you want DS3's community half; approval is manual now.
5. **Re-read all six.** This audit is a snapshot of September 2026.
