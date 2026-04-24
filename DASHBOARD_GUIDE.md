# Polymarket Streaming Dashboard Beginner Guide

## What The Bot Does

This is a pure Polymarket trader, not a Bitcoin spot trader. Every 15 minutes
Polymarket opens a binary market: "Will BTC be above or below barrier X at time
T?", priced from $0.00 to $1.00. The bot:

1. Prices the fair probability of each side using BTC options math.
2. Compares that model probability to the Polymarket market price.
3. Buys YES shares on the UP or DOWN side only when the model sees enough edge.
4. Exits on TP, SL, or window expiry.

## Top Row

### Model Probabilities Vs Market

Shows the bot's computed probability of each side from available models:

- SSVI surface.
- SSVI + Monte Carlo.
- Optional Heston output if computed.
- Average / used probability.

The bars compare the model's fair probability to the Polymarket quote. `used`
means that probability is feeding the strategy. `n/a` means the model has not
produced a usable value yet.

### Edge Ratio

The ratio of model probability versus Polymarket price, per side. The bot only
enters when:

- `cur` is greater than or equal to `req`.
- The 15-minute market is inside the tradeable zone.
- The live order can satisfy the configured FOK/max-price rules.

Red means blocked; green means open. The chip says `hold` or `none` to show the
current strategy state.

## Price Chart

The BTC UP/DOWN chart shows Polymarket's live bid/ask probability as solid
lines and the bot's model probabilities as dashed lines. Green is UP, rose is
DOWN. Colored zones mark no-entry periods at the start and end of each
15-minute cycle.

## Middle Row

### Current Market

The active Polymarket contract is named like `btc-updown-15m-<epoch>`. The small
UP/DOWN chip is Polymarket's framing of the YES side, not a standalone bot
signal. This panel also shows BTC spot, barrier, bid/ask, and time left.

### 15-Min Window

The progress bar is split into:

- First 5 minutes blocked: barrier settling.
- Minutes 5-13 tradeable: entries allowed.
- Last 2 minutes blocked: exits only.

### Position

Shows either flat/waiting state or the active trade: side, entry price, shares,
TP, SL, and notional.

## Bottom Row

### Performance Card

All-time metrics include capital, total PnL, Sharpe, max drawdown, win rate,
trade count, days live, and capped CAGR.

Today metrics show closed trades on the dashboard's trading day: PnL, positions,
and win rate.

Parameter chips show the active strategy constants:

- `aU / aD`: alpha up/down.
- `fU / fD`: floor up/down.
- `tp`: take-profit target.
- `sl`: stop-loss target, or `off` if disabled.

### Equity Curve

Dollar equity over time, baseline pinned at the configured starting capital.

### Trade Feed

Every event appears in reverse chronological order:

- `ENTRY`: position opened.
- `TP_FILLED` / `WIN_EXPIRY`: profitable exit.
- `STOP_LOSS` / `LOSS_EXPIRY`: losing exit.

Entry and exit prices plus dollar/percent PnL are shown per row.

## Footer And Status Chips

- `backend / ws / bot`: health dots.
- `last tick`: seconds since the last backend heartbeat.
- `location`: local or the selected VPS profile, plus active-side Polymarket latency.
- `model`: whether a usable probability calculation has arrived, which side produced it, and the spacing between usable updates.
- `fit / mc`: latest surface-fit and Monte Carlo compute times.

When live runs on a VPS, the dashboard itself still runs locally. The VPS trader
executes orders and writes live state, the local sync loop mirrors that state
back for display, and local calibration offload may send probability events to
the VPS trader alongside the VPS trader's own calculations.

## Strategy In One Sentence

Enter YES on whichever side's model probability sufficiently exceeds
Polymarket's quote, then ride to TP, SL, or market expiry.
