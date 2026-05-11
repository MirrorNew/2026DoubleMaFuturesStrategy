# 5/10/30 六均线密集合约策略说明

更新日期：2026-05-11

本文档记录当前 `VideoDoubleMaFuturesStrategy` 的实际策略逻辑。当前版本已经从旧的 `20/60/120` 六均线，改为 `5/10/30` 六均线；密集区也从单纯宽度收敛，改为更接近人工红框观察的“走平、粘合、组距收缩、价格横盘”。

## 1. 回测仓位语义

你的真实交易意图是：

- 账户本金：`10000 USDT`
- 单次开仓保证金：`100 USDT`
- 杠杆：`100x`
- 单次名义仓位：`100 * 100 = 10000 USDT`
- 账户有 `10000 USDT` 作为全仓风险缓冲，所以账户有效杠杆约等于 `1x`

由于 Freqtrade 2026.4 当前不支持 Gate 的 cross futures 回测，本策略采用等效回测法：

- Freqtrade 回测 stake：`10000 USDT`
- Freqtrade 回测 leverage：`1x`
- 等效真实开仓：`100 USDT 保证金 * 100x`
- 回测账户收益率乘以 `100`，大致等于真实 `100U` 保证金视角收益率

示例：

- 回测账户收益 `+2%`，约等于 `100U` 保证金收益 `+200%`
- 回测账户亏损 `-3%`，约等于 `100U` 保证金收益 `-300%`

策略层灾难止损为账户维度 `-3%`，等效真实保证金视角 `-300%`。

## 2. 当前使用的六条均线

策略使用：

- `MA5`
- `EMA5`
- `MA10`
- `EMA10`
- `MA30`
- `EMA30`

颜色约定：

- `5` 线：蓝绿色系
- `10` 线：黄色系
- `30` 线：紫色系

均线束定义：

- `ma_high = 六条均线中的最高值`
- `ma_low = 六条均线中的最低值`
- `ma_width = (ma_high - ma_low) / close`

三组中值：

- `fast_mid = (MA5 + EMA5) / 2`
- `mid_mid = (MA10 + EMA10) / 2`
- `slow_mid = (MA30 + EMA30) / 2`

## 3. 当前均线密集定义

当前密集区模仿你图中红框 1-5 的人工观察：不是只看六线最窄，而是要求六条线接近走平、彼此粘合、5/10/30 三组距离收缩，价格在均线束附近横盘。

一根 K 线成为密集候选，需要同时满足以下条件。

### 3.1 六线粘合

```text
ma_width <= 2.5%
```

即六条均线的最高值和最低值之间的距离，不超过当前价格的 `2.5%`。

### 3.2 相对收敛或近期明显收缩

满足以下任意一个条件：

```text
ma_width <= 过去 180 根 K 线 ma_width 的 55% 分位数
```

或者：

```text
ma_width <= 最近 24 根 K 线最大 ma_width * 0.92
```

第二条用来识别“最近正在压缩”的均线团，即使它不是长期历史里最窄的区域。

### 3.3 六线斜率接近走平

每条均线都计算最近 `6` 根 K 线的变化率：

```text
abs(当前均线值 / 6 根前均线值 - 1)
```

六条均线中最大的变化率必须：

```text
ma_max_flat_slope <= 1.2%
```

这对应人工观察里的“线开始横着走，不再快速发散”。

### 3.4 5/10/30 三组距离逐步收缩

先计算三组均线中值：

```text
fast_mid = (MA5 + EMA5) / 2
mid_mid  = (MA10 + EMA10) / 2
slow_mid = (MA30 + EMA30) / 2
```

再计算三组之间的最大距离：

```text
group_spread = (max(fast_mid, mid_mid, slow_mid) - min(fast_mid, mid_mid, slow_mid)) / close
```

当前三组距离必须比 `12` 根 K 线前更收缩：

```text
group_spread <= group_spread.shift(12) * 0.92
```

这对应你说的“20 / 60 / 120 三组线之间距离逐步收缩”，在当前版本里等价替换为 `5 / 10 / 30` 三组线之间距离逐步收缩。

### 3.5 价格在均线束附近横盘

最近 `12` 根 K 线的高低点区间：

```text
price_range = rolling_high_12 - rolling_low_12
```

满足以下任意一个：

```text
price_range <= 3.2 * ATR14
```

或者：

```text
price_range / close <= 4.5%
```

这用于避免把单边快速穿越均线束的走势误判为密集横盘。

### 3.6 价格靠近均线束

收盘价必须位于：

```text
ma_low - 1.2 * ATR14
到
ma_high + 1.2 * ATR14
```

之间。

### 3.7 多根确认

不是一根 K 线满足就算密集区。

确认条件：

```text
最近 6 根 K 线中，至少 4 根是密集候选
```

确认后：

```text
ma_cluster_confirmed = True
```

画图里的 cluster 矩形框，就是按连续的 `ma_cluster_confirmed` 区间画出来的。

## 4. 密集突破开仓

确认密集区后，策略记录：

- 密集区上沿：`cluster_zone_high`
- 密集区下沿：`cluster_zone_low`

密集区结束后，最多等待 `96` 根 K 线寻找突破。每个密集区最多产生一次突破信号。

### 4.1 多头突破

做多突破需要满足：

1. 收盘价向上突破密集区上沿
2. 突破缓冲至少为：
   ```text
   max(close * 0.1%, 0.12 * ATR14)
   ```
3. 前一根 K 线尚未有效站上密集区上沿
4. 当前 K 线为阳线
5. 均线多头排列：
   ```text
   fast_mid > mid_mid > slow_mid
   ```
6. 收盘价位于六均线上方

触发后，记录该突破 K 线的实体下沿：

```text
breakout_body_low = min(open, close)
```

### 4.2 空头突破

做空突破需要满足：

1. 收盘价向下跌破密集区下沿
2. 跌破缓冲至少为：
   ```text
   max(close * 0.1%, 0.12 * ATR14)
   ```
3. 前一根 K 线尚未有效跌破密集区下沿
4. 当前 K 线为阴线
5. 均线空头排列：
   ```text
   fast_mid < mid_mid < slow_mid
   ```
6. 收盘价位于六均线下方

触发后，记录该突破 K 线的实体上沿：

```text
breakout_body_high = max(open, close)
```

## 5. 突破后的第一次回踩开仓

回踩信号不能凭空出现，必须发生在一次有效密集突破之后。

突破后最多等待 `96` 根 K 线寻找第一次回踩或反抽。

### 5.1 多头第一次回踩

向上突破后，策略记录突破 K 线实体下沿：

```text
pullback_stop_long_line = min(open, close)
```

后面出现第一根真正回踩 K 线时，如果：

```text
low >= pullback_stop_long_line
```

则开多。

当前对“第一根真正回踩 K 线”的识别为满足以下任意一个：

- 当前收盘价低于前一根收盘价
- 当前最低价低于前一根最低价
- 当前 K 线为阴线

不再要求回踩 5 线，也不要求回踩 K 线必须收阳。核心只看：第一次回踩是否守住突破 K 线实体下沿。

### 5.2 空头第一次反抽

向下跌破后，策略记录突破 K 线实体上沿：

```text
pullback_stop_short_line = max(open, close)
```

后面出现第一根真正反抽 K 线时，如果：

```text
high <= pullback_stop_short_line
```

则开空。

当前对“第一根真正反抽 K 线”的识别为满足以下任意一个：

- 当前收盘价高于前一根收盘价
- 当前最高价高于前一根最高价
- 当前 K 线为阳线

不再要求反抽 5 线，也不要求反抽 K 线必须收阴。核心只看：第一次反抽是否被突破 K 线实体上沿压住。

## 6. 止损

策略按入场类型使用不同止损。

### 6.1 密集突破单

多单止损：

- 连续两根 K 线有效跌破原密集区下沿
- 有效跌破加入 `0.15 * ATR14` 缓冲

空单止损：

- 连续两根 K 线有效突破原密集区上沿
- 有效突破加入 `0.15 * ATR14` 缓冲

### 6.2 突破后回踩单

多单止损：

- 跌破突破 K 线实体下沿失效
- 止损线为：
  ```text
  pullback_stop_long_line - 0.15 * ATR14
  ```

空单止损：

- 突破突破 K 线实体上沿失效
- 止损线为：
  ```text
  pullback_stop_short_line + 0.15 * ATR14
  ```

当前回测里对应的退出标签：

- `long_breakout_body_line_invalid`
- `short_breakout_body_line_invalid`

### 6.3 灾难止损

策略层灾难止损：

```text
stoploss = -3%
```

这是账户维度 `-3%`，等效真实 `100U` 保证金视角 `-300%`。

## 7. 止盈

止盈不是固定 ROI，而是根据该单止损点计算风险 `R`。

多单：

```text
R = 入场价 - 止损价
2R 目标 = 入场价 + 2R
3R 目标 = 入场价 + 3R
```

空单：

```text
R = 止损价 - 入场价
2R 目标 = 入场价 - 2R
3R 目标 = 入场价 - 3R
```

同时参考前 `120` 根 K 线：

- 多单看前高
- 空单看前低

止盈选择：

- 原则上盈亏比不能低于 `2:1`
- 如果前高/前低位于 `2R` 到 `3R` 之间，优先使用该结构位
- 如果结构位超过 `3R`，使用 `3R`
- 如果结构位不足 `2R` 或不可用，使用 `2R`

## 8. 大幅盈利移动止盈

真实保证金视角盈利达到 `+200%` 时，启动移动止盈。

在当前等效回测中：

```text
账户盈利 +2% ≈ 保证金盈利 +200%
```

启动后记录该单历史最大浮盈。

如果从最高浮盈回吐 `50%`，立即止盈。

示例：

- 最高浮盈 `+200%`，回落到 `+100%`，止盈
- 最高浮盈 `+300%`，回落到 `+150%`，止盈
- 最高浮盈 `+500%`，回落到 `+250%`，止盈

## 9. 当前 1h 回测结果

当前版本：`5/10/30` 六均线 + 走平粘合横盘密集 + 突破实体线第一次回踩。

回测文件：

`user_data/backtest_results/backtest-result-2026-05-11_19-16-48.zip`

回测区间：

- `2025-04-21 19:00:00` 到 `2026-05-10 16:00:00`

结果：

- 交易数：`1`
- BTC：`0` 笔
- ETH：`1` 笔
- 胜率：`0%`
- 总收益：`-47.33491033 USDT`
- 账户收益：`-0.47%`
- 保证金视角约：`-47.33%`
- 最大回撤：`47.33491033 USDT`
- 账户最大回撤：`0.47%`
- Profit Factor：`0`
- 退出原因：`short_breakout_body_line_invalid`

当前结果说明：

- 密集区矩形框已经能大量标注“走平粘合横盘区”
- 但交易仍然很少，主要卡在“密集结束后的有效突破”和“突破后第一根回踩守住实体线”
- 下一步如果要增加交易，需要优先放松突破条件，而不是再放松回踩条件

## 10. 画图代码位置

交易图脚本：

`scripts/plot_futures_trades.py`

可调区域：

- 均线颜色：`MA_COLORS`
- 矩形样式：`CLUSTER_RECTANGLE_STYLE`
- 矩形生成逻辑：`iter_cluster_rectangles()`
- 矩形绘制逻辑：`add_cluster_rectangles()`
- 日期局部图参数：`--date-from` 和 `--date-to`
- 关闭 cluster 矩形参数：`--hide-clusters`

生成带 cluster 图：

```powershell
& 'E:\my_evns\env_freqtrade\python.exe' .\scripts\plot_futures_trades.py `
  --backtest-zip .\user_data\backtest_results\backtest-result-2026-05-11_19-16-48.zip `
  --timeframe 1h `
  --output-dir .\reports\futures_backtests\plots_ma_5_10_30_body_pullback_1h
```

生成不带 cluster 图：

```powershell
& 'E:\my_evns\env_freqtrade\python.exe' .\scripts\plot_futures_trades.py `
  --backtest-zip .\user_data\backtest_results\backtest-result-2026-05-11_19-16-48.zip `
  --timeframe 1h `
  --output-dir .\reports\futures_backtests\plots_ma_5_10_30_body_pullback_1h_no_cluster `
  --hide-clusters
```

## 11. 最新图表

带 cluster：

- `reports/futures_backtests/plots_ma_5_10_30_body_pullback_1h/BTC_USDT_USDT-1h-futures-trades.html`
- `reports/futures_backtests/plots_ma_5_10_30_body_pullback_1h/ETH_USDT_USDT-1h-futures-trades.html`

关闭 cluster：

- `reports/futures_backtests/plots_ma_5_10_30_body_pullback_1h_no_cluster/BTC_USDT_USDT-1h-futures-trades.html`
- `reports/futures_backtests/plots_ma_5_10_30_body_pullback_1h_no_cluster/ETH_USDT_USDT-1h-futures-trades.html`

## 12. 主要可调参数

密集宽度：

```python
ma_cluster_width_threshold = 0.025
```

斜率走平：

```python
ma_flat_slope_lookback = 6
ma_flat_slope_threshold = 0.012
```

三组距离收缩：

```python
ma_group_contract_window = 12
ma_group_contract_ratio = 0.92
```

价格横盘：

```python
sideways_lookback = 12
sideways_range_atr_max = 3.2
sideways_range_pct_max = 0.045
```

突破后等待回踩：

```python
cluster_breakout_window = 96
pullback_window = 96
```

突破实体线容忍度：

```python
breakout_body_line_tolerance = 0.0
```

如果你希望“轻微刺破突破实体线也算没破”，可以把它改成比如：

```python
breakout_body_line_tolerance = 0.001
```

即允许 `0.1%` 的刺破。

## 13. 当前主要问题

当前策略更贴近人工识别密集区，但还不是成熟盈利策略。

主要问题：

1. cluster 框很多，但有效突破交易很少。
2. 当前突破要求仍然偏严格：必须突破密集区上下沿，并且满足方向 K 线和均线排列。
3. 只等待“第一根”回踩，如果第一根失败，后续不会继续等第二根。
4. BTC 在当前 1h 数据内没有交易，说明 BTC 的有效突破过滤过强。
5. 下一步更适合把“突破”分成强突破和弱突破，而不是继续放松密集区。
