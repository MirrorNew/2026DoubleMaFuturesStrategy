# Monte Carlo Stress Test

本报告用于压力测试当前 ETH 双均线策略，而不是用于证明策略一定有效。模型刻意加入肥尾、波动率聚集、日内/周内波动差异、跳跃风险、真实 BTC/ETH return block bootstrap，以及低概率黑天鹅路径。

- 每个场景模拟次数：`20`
- 数据频率：`1h`
- 回测执行：轻量执行器复刻当前策略的入场、计划结构止损、R 倍止盈和移动止盈；结果用于压力测试，不替代 Freqtrade 正式回测。
- 变体：`stable_default` 为当前稳定版；`simple_long_continuation` 为 4h + 1d 多头确认后的简单只做多趋势中继增强。

![Monte Carlo median equity curves](monte_carlo/monte_carlo_equity_curves.svg)

## Summary Table

| Variant | Scenario | Sims | Median CAGR | P05 CAGR | Median Return | P05 Return | Median DD | P95 DD | Median Winrate | Median PF | Loss Prob | Ruin Prob | Median Trades |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| simple_long_continuation | black_swan_crash_rebound | 20 | 12.27% | -20.48% | 78.35% | -67.58% | 47.89% | 78.21% | 43.41% | 1.15 | 40.00% | 0.00% | 262 |
| simple_long_continuation | black_swan_slow_decay | 20 | 1.16% | -19.37% | 5.96% | -65.85% | 54.58% | 68.39% | 43.63% | 1.04 | 40.00% | 0.00% | 256 |
| simple_long_continuation | historical_eth_btc_bootstrap | 20 | -44.44% | -53.37% | -94.70% | -97.74% | 95.32% | 98.27% | 30.61% | 0.55 | 100.00% | 0.00% | 272 |
| simple_long_continuation | t_clustered_calendar_jump | 20 | 3.54% | -19.19% | 19.02% | -65.31% | 48.53% | 78.30% | 43.11% | 1.09 | 35.00% | 0.00% | 255 |
| stable_default | black_swan_crash_rebound | 20 | 13.79% | -6.13% | 91.09% | -26.30% | 38.25% | 69.57% | 45.66% | 1.21 | 25.00% | 0.00% | 216 |
| stable_default | black_swan_slow_decay | 20 | 11.16% | -6.61% | 69.77% | -28.93% | 41.43% | 61.41% | 46.36% | 1.18 | 20.00% | 0.00% | 213 |
| stable_default | historical_eth_btc_bootstrap | 20 | -34.34% | -43.40% | -87.73% | -94.04% | 88.92% | 95.03% | 34.80% | 0.60 | 100.00% | 0.00% | 205 |
| stable_default | t_clustered_calendar_jump | 20 | 12.19% | -6.76% | 77.77% | -29.52% | 40.34% | 65.14% | 46.59% | 1.19 | 15.00% | 0.00% | 213 |

## Strategy Analysis

- 中位数年化最高的是 `stable_default` / `black_swan_crash_rebound`，median CAGR 为 `13.79%`，但需要同时看 P95 回撤 `69.57%`。
- 最脆弱的左尾来自 `simple_long_continuation` / `historical_eth_btc_bootstrap`，P05 return 为 `-97.74%`；这说明遇到连续跳跃或逐渐归零类路径时，双均线系统无法保证保本。
- 稳定版的优点是规则更短、暴露更少；趋势中继版在部分趋势路径中更敢追，但在震荡后接跳跃的路径上会增加额外亏损。
- 这个压力测试支持的结论是：趋势中继可以作为手动判断强趋势时的开关，不建议永远开启；主系统仍应以均线密集突破/首次回踩为核心。
- 黑天鹅路径下最重要的不是提高胜率，而是限制单笔风险和避免高频重复进场；实盘仍需要交易所止损、最大日亏损、连续亏损暂停等执行层保护。

## Files

- `reports/futures_backtests/monte_carlo/monte_carlo_detail.csv`
- `reports/futures_backtests/monte_carlo/monte_carlo_summary.csv`
- `monte_carlo/monte_carlo_equity_curves.svg`
- `reports/futures_backtests/monte_carlo/monte_carlo_stress_summary.json`
