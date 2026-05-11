# ETH 2x False Breakout Refinement

Date: 2026-05-12

## Overall Judgment

I am not 100% confident this is a live-ready strategy, but this version is materially better aligned with the current goal: reduce bad false-breakout losses and raise realized payoff while keeping ETH-only, 1h execution, 4h context, and 2x effective exposure.

The most important finding is that the original `body_line_invalid` logic was too slow because it waited for candle-close confirmation. That made failed breakouts lose more than a manual trader would usually tolerate. The fix is not mainly another discretionary early-exit rule; the better fix is to convert the planned structure stop into an actual `custom_stoploss`.

## Final Default System

- Pair: `ETH/USDT:USDT`
- Timeframe: `1h`
- Higher timeframe: `4h`
- Direction: long and short
- Max open trades: `1`
- Effective exposure: `2x`
- Entry family: 5/10/30 MA + EMA compression breakout and first pullback confirmation
- 4h filter: enabled by default
- Minimum target: `2.3R`
- Preferred target: `3.5R`
- Normal maximum structure target: `5R`
- Strong trend maximum structure target: `7R`
- Normal trailing: disabled
- Strong trend trailing: enabled only after `+5%`, allowing `60%` giveback
- Extra 1-2 candle early false-breakout exit: disabled by default
- Structure stop: enabled through `custom_stoploss`

## What Changed

1. Added real structure stop execution:
   - The strategy now calculates the planned stop from the entry candle.
   - For pullback entries, the stop is based on the breakout body line, cluster boundary, and valid pivot structure.
   - The planned stop is converted to a Freqtrade stoploss through `stoploss_from_absolute`.
   - This reduces the old problem where `body_line_invalid` exited only after the candle closed.

2. Raised payoff target:
   - Minimum take-profit moved from `2.0R` to `2.3R`.
   - Preferred target moved from `3.0R` to `3.5R`.
   - Strong trend target ceiling moved from `6R` to `7R`.

3. Re-enabled 4h directional filtering:
   - This cuts some low-quality entries.
   - It reduces trade count, but improves validation quality.

4. Adjusted trailing:
   - Ordinary trades no longer use moving take-profit.
   - Only 4h strong-trend trades trail, and only after a larger profit cushion.

5. Disabled the extra early false-breakout exit by default:
   - The first implementation had a loophole: it could still trigger after the intended early window.
   - After fixing that, the rule was still noisy and reduced performance.
   - The actual early recognition is now handled by the structural stop.

## Final Backtest Results

### Training: 2021-05-11 to 2025-01-01

| Metric | Value |
|---|---:|
| Trades | 215 |
| Total profit | 100.84% |
| CAGR | 21.46% |
| Winrate | 34.88% |
| Profit factor | 1.345 |
| Max drawdown | 17.72% |
| Sharpe | 0.339 |
| Sortino | 1.135 |
| Avg win | 5.24% |
| Avg loss | 2.09% |
| Realized payoff | 2.51 |
| Body-line invalid exits | 4 |
| Stoploss exits | 27 |
| Long profit | 99.22% |
| Short profit | 1.63% |

Backtest file: `user_data/backtest_results/backtest-result-2026-05-12_01-23-26.zip`

### Validation: 2025-01-01 to 2026-05-11

| Metric | Value |
|---|---:|
| Trades | 76 |
| Total profit | 53.04% |
| CAGR | 36.94% |
| Winrate | 39.47% |
| Profit factor | 1.591 |
| Max drawdown | 18.54% |
| Sharpe | 0.512 |
| Sortino | 1.629 |
| Avg win | 4.77% |
| Avg loss | 1.95% |
| Realized payoff | 2.44 |
| Body-line invalid exits | 2 |
| Stoploss exits | 9 |
| Long profit | 30.27% |
| Short profit | 22.77% |

Backtest file: `user_data/backtest_results/backtest-result-2026-05-12_01-23-42.zip`

### Full Range: 2021-05-11 to 2026-05-11

| Metric | Value |
|---|---:|
| Trades | 291 |
| Total profit | 154.24% |
| CAGR | 20.78% |
| Winrate | 36.08% |
| Profit factor | 1.404 |
| Max drawdown | 13.51% |
| Sharpe | 0.383 |
| Sortino | 1.266 |
| Avg win | 5.11% |
| Avg loss | 2.05% |
| Realized payoff | 2.49 |
| Body-line invalid exits | 6 |
| Stoploss exits | 36 |
| Long profit | 129.49% |
| Short profit | 24.75% |

Backtest file: `user_data/backtest_results/backtest-result-2026-05-12_01-24-32.zip`

## Comparison Against Previous Best

Previous best:

- Training CAGR: `24.05%`
- Validation CAGR: `29.51%`
- Full CAGR: `21.19%`
- Full realized payoff: about `1.51`
- Training `body_line_invalid` exits: `127`

New version:

- Training CAGR: `21.46%`
- Validation CAGR: `36.94%`
- Full CAGR: `20.78%`
- Full realized payoff: `2.49`
- Training `body_line_invalid` exits: `4`

The new version gives up a little training and full-range CAGR, but it strongly improves the failure-breakout problem and validation period quality.

## Remaining Loopholes

1. The short side is still weaker in the long training period. It improves in validation, but should not be assumed stable.
2. Realized payoff is near `2.5`, not `3.0`. Pushing to full `3R` may reduce winrate and CAGR.
3. Stoploss exits are now more realistic, but backtests still cannot perfectly model slippage during violent candles.
4. The strategy remains sensitive to the 4h filter. Turning it off increases trade count but worsens validation quality.
5. The system is still not a replacement for manual context reading around major macro events.

## Suggested Next Adjustments

1. Split long and short parameters. The long side can remain more aggressive; shorts need stricter regime control.
2. Add volatility regime scoring. Avoid ETH entries when compression appears inside low-energy chop instead of pre-trend accumulation.
3. Test `VDM_RR_MIN=2.5` only on strong-trend trades, while keeping weak trades at `2.3R`.
4. Keep `VDM_EARLY_FAIL_WINDOW=0` unless visual review shows specific failures that the structure stop cannot catch.
5. Use yearly walk-forward checks before considering dry-run.
