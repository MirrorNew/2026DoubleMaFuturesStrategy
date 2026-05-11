# ETH 2x Annualized Exploration

Date: 2026-05-12

## Goal

Explore an ETH-only 1h futures version that prioritizes annualized return, while keeping winrate above 30% and using at most 2x effective account leverage.

## Current Best Candidate

- Pair: `ETH/USDT:USDT`
- Base timeframe: `1h`
- Informative timeframe: `4h`
- Effective leverage: `2x`
- Max open trades: `1`
- Weekend mode: normal entries enabled
- 4h usage: trend context, not a hard entry filter
- Trend runner: strong 4h trend can extend structure target up to `6R`
- Global stoploss: `-6%` account return, matching 2x effective leverage

## Split Results

### Training / Parameter Observation: 2021-06-01 to 2025-01-01

| Metric | Value |
|---|---:|
| Trades | 264 |
| Total profit | 116.61% |
| CAGR | 24.05% |
| Winrate | 45.08% |
| Max drawdown | 13.94% |
| Profit factor | 1.29 |
| Sharpe | 0.38 |
| Sortino | 1.03 |
| Calmar | 12.21 |
| Avg win | 4.36% |
| Avg loss | 2.77% |
| Payoff ratio | 1.57 |
| Long profit | 120.27% |
| Short profit | -3.65% |
| Max consecutive losses | 10 |

### Validation: 2025-01-01 to 2026-05-10

| Metric | Value |
|---|---:|
| Trades | 96 |
| Total profit | 41.91% |
| CAGR | 29.51% |
| Winrate | 48.96% |
| Max drawdown | 13.35% |
| Profit factor | 1.31 |
| Sharpe | 0.41 |
| Sortino | 1.06 |
| Calmar | 12.14 |
| Avg win | 3.73% |
| Avg loss | 2.73% |
| Payoff ratio | 1.37 |
| Long profit | 16.27% |
| Short profit | 25.64% |
| Max consecutive losses | 6 |

### Full Range: 2021-06-01 to 2026-05-10

| Metric | Value |
|---|---:|
| Trades | 360 |
| Total profit | 158.52% |
| CAGR | 21.19% |
| Winrate | 46.11% |
| Max drawdown | 13.94% |
| Profit factor | 1.30 |
| Sharpe | 0.39 |
| Sortino | 1.03 |
| Calmar | 12.04 |
| Avg win | 4.18% |
| Avg loss | 2.76% |
| Payoff ratio | 1.51 |
| Long profit | 136.54% |
| Short profit | 21.98% |
| Max consecutive losses | 10 |

## Interpretation

The best candidate does not yet meet a stable 30% CAGR target. It gets close on the 2025-2026 validation period at 29.51%, but the 2021-2024 training period is 24.05%, and the full five-year CAGR is 21.19%.

The strategy does satisfy the winrate floor. Winrate remains between 45% and 49% across the split tests.

The actual average payoff ratio is still below 3:1. The code targets structure exits around 2R-6R depending on trend context, but actual exits include early structural invalidations, stoplosses, and trailing giveback exits. Therefore the realized average payoff is closer to 1.4-1.6.

The largest remaining weakness is short-side quality. In the 2021-2024 split, long trades account for nearly all profit while short trades are slightly negative. In 2025-2026, shorts perform better, so removing shorts outright would likely overfit.

## Next Directions

1. Split long and short parameters. Long entries can stay more aggressive; short entries likely need stricter filters in older market regimes.
2. Add a market regime filter. The system should distinguish high-volatility trend expansion from choppy compression failure.
3. Improve realized payoff. Reduce early trailing exits in strong trend, but only after adding better failure detection.
4. Test 4h context as a soft score instead of binary filter. Current hard filtering reduces annualized return too much.
5. Add walk-forward validation over yearly folds before treating the 2x version as a candidate for dry-run.
