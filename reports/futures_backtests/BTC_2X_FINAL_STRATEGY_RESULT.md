# BTC 2x Strategy Backtest Result

Date: 2026-05-12

## Summary

The current ETH-tuned double MA futures strategy does not transfer well to BTC.

BTC validation is acceptable but not strong. The full-range result is weak because the 2021-2024 training period has low CAGR and very high drawdown. The main weakness is the short side, which loses money in all three splits.

## Data Note

The first BTC run returned zero trades because BTC 4h informative data was missing while the strategy requires a 4h filter. I generated BTC 4h candles from the local BTC 1h futures data, then reran the backtest.

## BTC Results

| Period | Trades | CAGR | Total Profit | Winrate | Profit Factor | Max DD | Avg Win | Avg Loss | Payoff |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021-05-11 to 2025-01-01 | 227 | 5.51% | 21.23% | 34.80% | 1.074 | 45.78% | 4.62% | 2.22% | 2.08 |
| 2025-01-01 to 2026-05-11 | 77 | 19.76% | 27.65% | 33.77% | 1.288 | 15.27% | 4.77% | 1.89% | 2.53 |
| 2021-05-11 to 2026-05-11 | 304 | 8.41% | 49.02% | 34.54% | 1.128 | 45.78% | 4.65% | 2.14% | 2.18 |

## Long / Short Split

| Period | Long Trades | Long Profit | Short Trades | Short Profit |
|---|---:|---:|---:|---:|
| 2021-05-11 to 2025-01-01 | 120 | 26.35% | 107 | -5.12% |
| 2025-01-01 to 2026-05-11 | 34 | 30.52% | 43 | -2.87% |
| 2021-05-11 to 2026-05-11 | 154 | 57.01% | 150 | -7.99% |

## Exit Quality

| Period | Stoploss Count | Stoploss Avg | TP Count | TP Avg | Trailing Count | Trailing Avg | Body Invalid Count |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021-05-11 to 2025-01-01 | 54 | -3.18% | 69 | 4.80% | 10 | 3.37% | 6 |
| 2025-01-01 to 2026-05-11 | 12 | -3.08% | 18 | 5.13% | 7 | 3.71% | 2 |
| 2021-05-11 to 2026-05-11 | 66 | -3.16% | 87 | 4.87% | 17 | 3.51% | 8 |

## Conclusion

Do not use the current ETH version directly on BTC.

BTC has a reasonable realized payoff, but the expectancy is too thin and the drawdown is unacceptable in the training/full periods. The BTC short side is consistently negative, so the first BTC-specific fix should be either disabling shorts or adding a much stricter BTC short regime filter.

For now, ETH remains the better target for this strategy.

## Backtest Files

- Training: `user_data/backtest_results/backtest-result-2026-05-12_01-44-34.zip`
- Validation: `user_data/backtest_results/backtest-result-2026-05-12_01-45-11.zip`
- Full: `user_data/backtest_results/backtest-result-2026-05-12_01-46-22.zip`
- JSON summary: `reports/futures_backtests/btc_2x_final_strategy_results.json`
