# stock-bot — a nightly analyst board, delivered through Muse

Every weekday evening after the US close this job pulls daily prices for Farhaan's watchlist, applies a fixed set of rules, and writes three markdown files into his `life-inbox` repo. Muse (his Meta agent) reads them at 10 PM PT, adds what the news says moved each flagged name, and pushes the brief to his phone. He reads it, does his own research, and places (or doesn't place) his own orders in the morning.

The brief is written in plain words (the full numbers and the rule jargon stay in `latest.md`).

**Nothing here trades, holds a brokerage login, or connects to any account. Every number comes from a data feed; the rules are code; the only words a model writes are Muse's "what sources say" lines.**

## What it is
Two engines share three slots on an 18-name AI-infrastructure list:
- **Engine L (leaders):** a name in the top 6 of the list by 63-day return, beating SMH and above its 50-day, whose RSI(2) closes under 15. Exit 10% off the highest close since entry, −10% hard stop, or 40 sessions.
- **Engine D (deep dips):** a close at least max(15%, 1.5 × monthly volatility) below the 21-day high. Exit 8% off the highest close, −10% hard stop, or 20 sessions. Printed plus: still above its 200-day.
- **Skips:** earnings within 5 sessions ahead or 3 behind, a 20% one-day drop in the last 5, a news flag (offering, guidance cut, investigation, delisting…), a lock-up within 10 sessions.
- **Regime:** three slots while SMH is above its 200-day average, one slot below it.
- **Morning:** entries next day only, void if the name opens 3% above the close, limit orders cancelled at noon PT.

The rules, their evidence and three rounds of stress tests live in his private workspace (`projects/stock-bot/PLAN.md`); `board.py`, `engine2.py`, `stress3.py` and the `s3_*.py` scripts are the backtests that produced them. Honest expectation from eight years of no-hindsight data: about +6% a trade, 37 trades a year, half winners, one losing year in six.

## Files
| File | What |
|---|---|
| `nightly.py` | the job: fetch → rules → `brief.md` (phone-length), `latest.md` (full board), `YYYY-MM-DD.md` |
| `universe.py` | the list, company names for news, the 100-name pool for the monthly screen, lock-ups, macro dates, news-flag words |
| `engine2.py` | indicators and signal rules (shared with the backtests) |
| `deploy/life-inbox-stocks.yml` | the GitHub Actions workflow; the live copy is `.github/workflows/stocks.yml` in `life-inbox` |
| `backtest.py` `engine2.py` `stress3.py` `s3_*.py` `fetch*.py` | research code, rounds 1–3 |

## Run it
```
pip install -r requirements.txt
python nightly.py --out stocks --cache cache --positions stocks/positions.md [--screen]
```
`--screen` prints the monthly mechanical screen (top 18 of the pool by 6-month return); it also prints itself on the first trading day of each month. `--date YYYY-MM-DD` rebuilds an old close.

## Deploy (one-time)
1. This repo is public on GitHub as `Farhaanp9/stock-bot` (no secrets in it; the workflow checks it out without a token).
2. The workflow lives in the private `life-inbox` repo and writes `stocks/` there with that repo's own Actions token (`permissions: contents: write` in the YAML; no personal token needed).
3. Schedule: 01:45 UTC Tue–Sat, i.e. 6:45 PM PDT / 5:45 PM PST Monday to Friday. Run it by hand from the Actions tab (`stocks nightly` → Run workflow) any time.
4. Data: Yahoo Finance (unofficial, free) for prices, earnings dates and fundamentals; Google News RSS for headlines. If a fetch fails the board says so in its first line instead of guessing. A second price feed is an open item.

## Positions
`stocks/positions.md` in `life-inbox`: one line per holding, `- TICKER | L or D or own | entry PRICE | since YYYY-MM-DD | note`. Muse appends when he says "bought X at Y"; the job prints that name's exit levels every night.
