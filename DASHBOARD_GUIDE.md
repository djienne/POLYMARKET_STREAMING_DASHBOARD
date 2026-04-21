# Polymarket Streaming Dashboard — Beginner Guide

## What the bot does
This is a **pure Polymarket trader**, not a Bitcoin trader. Every 15 minutes Polymarket opens a binary market: *"Will BTC be ABOVE or BELOW barrier X at time T?"*, priced from $0.00 (certain No) to $1.00 (certain Yes). The bot:
1. **Prices the fair probability** of that YES/NO using BTC options math (Deribit IV surface + Heston + Monte-Carlo).
2. Compares its model probability to the **Polymarket market price**.
3. **Buys YES shares** (UP or DOWN side) only when the model thinks the market is mispriced in its favor — an **edge**.
4. Exits on **TP** (take profit), **SL** (stop loss), or **window expiry** (market resolves at T).

---

## Top row

### Model probabilities vs market
Shows the bot's computed probability of each side (UP / DOWN) from four models:
- **SSVI surface (BL)** — Black-Scholes barrier price from the fitted implied-vol surface
- **SSVI + Monte Carlo** — MC simulation using that surface
- **Heston** — stochastic-vol closed-form (skipped by default)
- **Average** — blend the bot actually uses

The **bars** compare the model's fair probability to the Polymarket quote. `used` means this model is the one feeding the strategy. `n/a` means the surface hasn't fit yet.

### Edge ratio
The ratio of model prob vs. Polymarket price, per side. The bot only enters when:
- `cur` (current ratio) ≥ `req` (required ratio — the floor set in params), AND
- the window is in the tradeable zone.

Red = `blocked`, green = `open`. The chip says `hold` / `none` to show current state.

---

## Price chart (BTC UP/DOWN)
Polymarket's live bid/ask probability (solid lines) vs. the bot's model (dashed lines). Green = UP side, rose = DOWN side. You see how the model leads or lags the market tick-by-tick. Colored zones mark **no-entry windows** at the start (first 5 min) and end (last 2 min) of each 15-min cycle.

---

## Middle row

### Current market
The active Polymarket contract: `btc-updown-15m-<epoch>`. The small colored chip (**UP / DOWN**) is Polymarket's own framing of the binary — which side is the YES side. Not a bot signal. Shows spot BTC, barrier price, bid/ask on the YES share, time left.

### 15-min window
Progress bar through the current 15-min cycle, split into:
- `BLOCKED 5M` — first 5 minutes, no entries allowed (too volatile)
- `TRADEABLE 5–13M` — entries allowed
- `BLOCKED 2M` — last 2 minutes, exits only (no new positions)

### Position
Either `Flat — waiting for edge` (no position) or details of the open trade: side, entry price, shares, TP and SL targets, notional.

---

## Bottom row

### Performance card
**ALL TIME** (lifetime since first trade):
- `Capital` current equity · `Total PnL` · `Sharpe` · `Max DD` · `Win rate` · `Trades` · `Days live` · `CAGR` (annualized, capped at `>1000%`)

**TODAY** (closed trades on today's Paris calendar date):
- `PnL $` · `PnL %` (vs capital at start of day) · `Positions` opened · today's `Win rate`

**Params chips** (constants the strategy uses):
- `aU / aD` — **alpha up/down**, tail exponents in the fair-value computation
- `fU / fD` — **floor up/down**, minimum edge ratio required to enter each side
- `tp` — take-profit target (% from entry)
- `sl` — stop-loss target (% from entry; `off` if disabled)

### Equity curve
Dollar equity over time, baseline pinned at $1000 (starting capital). Auto-rotates every 60 seconds between **all-history** and **last-4-days** zoom so viewers see both shapes.

### Trade feed (right rail)
Every event in reverse chronological order. Each row = one event:
- `ENTRY` (cyan highlight on new) — position opened, shows direction
- `TP_FILLED` / `WIN_EXPIRY` (green) — exit at profit, either by hitting TP target or resolving in-the-money
- `STOP_LOSS` / `LOSS_EXPIRY` (rose) — exit at loss, either by SL hit or resolving out-of-the-money

Entry → exit prices and $ / % PnL shown per row.

---

## Footer
- `backend / ws / bot` — live status dots (green = healthy)
- `last tick` — seconds since the last backend heartbeat
- `tz Europe/Paris · UTC+2 (CEST)` — all timestamps are Paris wall-clock; offset follows DST automatically
- `fit / mc` — latest surface-fit and Monte-Carlo compute times (ms of the last iteration)

---

## The strategy in one sentence
> Enter YES on whichever side's model probability sufficiently exceeds Polymarket's quote (edge ≥ floor), ride to TP or SL or market expiry, and keep doing it 15 minutes at a time.
