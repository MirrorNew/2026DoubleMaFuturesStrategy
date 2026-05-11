# Gate 合约多空版六均线策略回测报告

生成时间：2026-05-11  
策略：`VideoDoubleMaFuturesStrategy`  
配置：`config/config_gate_futures.json`

## 重要结论

当前合约多空版不满足实盘需要。  
我可以确认最新版代码在 1h 主周期审计中没有检测到未来函数偏差，但回测结果显示：在 100x 杠杆、每笔 100U 保证金下，账户几乎归零。

## 配置与限制

- 初始资金：`10000 USDT`
- 每笔保证金：`100 USDT`
- 杠杆：`100x`
- 最大同时持仓：原回测为 `2`；后续已按人工操作习惯改为 `1`
- 实际回测模式：`isolated futures`
- 原计划 `cross futures` 已测试，但 Freqtrade 2026.4 明确报错：`Freqtrade does not support 'cross' 'futures' on Gate.` 因此已按计划降级为逐仓。
- 最新策略止损意图已改为 `stoploss = -3.0`，即每笔 100U 保证金最多接受 -300% 策略收益。但在 100x 逐仓下，交易所强平通常会早于 -300%，所以这不能保证实盘能扛到 300U 亏损。
- Gate 合约 K 线存在约 10000 根历史限制：
  - `1h` 主数据：2025-04-01 到 2026-05-10
  - `4h` 对照数据：2022-01-01 到 2026-05-10

## 1h 主回测

- 回测区间：2025-04-21 19:00:00 到 2026-05-10 16:00:00
- 交易次数：1036
- 多 / 空：494 / 542
- 最终余额：84.313 USDT
- 总收益：-9915.687 USDT
- 总收益率：-99.16%
- 胜率：21.24%
- Profit factor：0.79
- 最大回撤：99.17%
- 最大连续亏损：20
- 平均持仓：3:58:00

分币种：

- `BTC/USDT:USDT`：492 笔，-49.37%
- `ETH/USDT:USDT`：544 笔，-49.78%

主要问题：

- `stop_loss` 触发 741 次，合计 -44370.771 USDT。
- ROI 交易本身合计盈利 +36540.717 USDT，但无法覆盖高频止损。
- 100x 下，-0.50 的 Freqtrade stoploss 约等于底层价格反向波动 0.5%，信号稍微抖动就会大面积止损。

## 4h 对照回测

- 回测区间：2022-03-25 04:00:00 到 2026-05-10 12:00:00
- 交易次数：883
- 多 / 空：392 / 491
- 最终余额：77.211 USDT
- 总收益：-9922.789 USDT
- 总收益率：-99.23%
- 胜率：22.20%
- Profit factor：0.76
- 最大回撤：99.23%
- 最大连续亏损：19
- 平均持仓：3:46:00

分币种：

- `ETH/USDT:USDT`：400 笔，-13.58%
- `BTC/USDT:USDT`：483 笔，-85.65%

## 审计结果

1h `lookahead-analysis`：

- `has_bias`：No
- `biased_entry_signals`：0
- `biased_exit_signals`：0
- `biased_indicators`：空

1h `recursive-analysis`：

- `startup_candle_count` 已从 180 提高到 499。
- `ma_width` 在 180 根时偏差约 -5.240%，499 根时约 0.060%，999 根时约 0.000%。
- 未发现指标未来函数偏差。

4h `lookahead-analysis`：

- `has_bias`：No
- `biased_entry_signals`：0
- `biased_exit_signals`：0

## 图表文件

只画开仓信号、不跑回测交易的图：

- `reports/futures_backtests/entry_signals/BTC_USDT_USDT-1h-entry-signals.html`
- `reports/futures_backtests/entry_signals/ETH_USDT_USDT-1h-entry-signals.html`
- `reports/futures_backtests/entry_signals/BTC_USDT_USDT-4h-entry-signals.html`
- `reports/futures_backtests/entry_signals/ETH_USDT_USDT-4h-entry-signals.html`

自定义 Plotly 图，明确显示 K 线、6 条均线、long/short 开平仓点：

- `reports/futures_backtests/plots/BTC_USDT_USDT-1h-futures-trades.html`
- `reports/futures_backtests/plots/ETH_USDT_USDT-1h-futures-trades.html`
- `reports/futures_backtests/plots/BTC_USDT_USDT-4h-futures-trades.html`
- `reports/futures_backtests/plots/ETH_USDT_USDT-4h-futures-trades.html`

Freqtrade 原生图：

- `user_data/plot/freqtrade-plot-BTC_USDT_USDT-1h.html`
- `user_data/plot/freqtrade-plot-ETH_USDT_USDT-1h.html`
- `user_data/plot/freqtrade-plot-BTC_USDT_USDT-4h.html`
- `user_data/plot/freqtrade-plot-ETH_USDT_USDT-4h.html`

## 下一轮必须修复的问题

1. 100x 与当前止损结构不兼容。若坚持 100x，入场必须极大幅减少，并且止损需要在入场前以更小的价格风险定义。
2. 当前“均线密集后突破”太宽，产生大量噪音信号。需要增加 ATR、实体比例、成交量和高周期趋势过滤。
3. 空头镜像逻辑亏损更重，尤其是 `short_cluster_breakout_down`。需要单独调空头，而不是机械镜像多头。
4. 当前 ROI 是静态 ROI，不是真正按入场结构计算的 R 倍数。下一版应记录入场结构止损价，再做 2R/3R/5R 测试。
5. 4h 对照使用 2022-2026 的 futures OHLCV，但 mark 数据只有 2025-04-01 以后；这不影响信号计算图，但会削弱更早区间的合约强平/资金费率还原可信度。
