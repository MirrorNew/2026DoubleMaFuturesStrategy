# 5/10/30 六均线密集合约策略说明（放松突破版）

更新日期：2026-05-11  
适用标的：BTC / ETH 永续合约  
核心修改：保留当前“均线密集区”识别逻辑，重点放松“突破确认”逻辑，将突破拆分为“强突破”和“弱突破”。

---

## 0. 修改目的

当前策略已经可以较好识别人工观察中的均线密集区。  
从图中红框 1-5 的走势来看，所谓“均线密集”并不一定是六条均线极窄地压缩在一起，而更接近以下形态：

1. 短中期均线逐渐靠拢；
2. 均线斜率变缓，整体开始走平；
3. 价格围绕均线束附近横盘；
4. 随后等待向上或向下选择方向。

因此，下一步不建议继续大幅放宽密集区条件。  
真正需要放松的是突破逻辑。

当前问题主要是：

1. 密集区可以被识别出来；
2. 但有效突破信号很少；
3. BTC 在 1h 回测中几乎没有交易；
4. 主要卡在“突破必须一次性满足完整方向确认”；
5. 尤其是完整均线排列 `fast_mid > mid_mid > slow_mid` 或 `fast_mid < mid_mid < slow_mid` 过于严格。

本版策略的修改目标是：

```text
密集区识别保持稳定；
突破确认从“单一强条件”改为“强突破 + 弱突破”两层结构；
强突破可以直接确认；
弱突破不直接开仓，而是等待回踩或反抽确认。
```

---

## 1. 回测仓位语义

真实交易意图：

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

---

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

```text
ma_high = 六条均线中的最高值
ma_low  = 六条均线中的最低值
ma_width = (ma_high - ma_low) / close
```

三组中值：

```text
fast_mid = (MA5 + EMA5) / 2
mid_mid  = (MA10 + EMA10) / 2
slow_mid = (MA30 + EMA30) / 2
```

---

## 3. 均线密集区定义

本策略中的密集区不是单纯要求六条均线宽度极窄，而是模仿人工观察中的“均线走平、粘合、组距收缩、价格横盘”。

一根 K 线成为密集候选，需要同时满足以下条件。

### 3.1 六线粘合

```text
ma_width <= 2.5%
```

即六条均线的最高值和最低值之间的距离，不超过当前价格的 `2.5%`。

对应参数：

```python
ma_cluster_width_threshold = 0.025
```

---

### 3.2 相对收敛或近期明显收缩

满足以下任意一个条件：

```text
ma_width <= 过去 180 根 K 线 ma_width 的 55% 分位数
```

或者：

```text
ma_width <= 最近 24 根 K 线最大 ma_width * 0.92
```

第二条用于识别“最近正在压缩”的均线团，即使它不是长期历史中最窄的区域。

---

### 3.3 六线斜率接近走平

每条均线都计算最近 `6` 根 K 线的变化率：

```text
abs(当前均线值 / 6 根前均线值 - 1)
```

六条均线中最大的变化率必须满足：

```text
ma_max_flat_slope <= 1.2%
```

对应参数：

```python
ma_flat_slope_lookback = 6
ma_flat_slope_threshold = 0.012
```

这对应人工观察里的“线开始横着走，不再快速发散”。

---

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

对应参数：

```python
ma_group_contract_window = 12
ma_group_contract_ratio = 0.92
```

---

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

对应参数：

```python
sideways_lookback = 12
sideways_range_atr_max = 3.2
sideways_range_pct_max = 0.045
```

---

### 3.6 价格靠近均线束

收盘价必须位于以下区间：

```text
ma_low - 1.2 * ATR14
到
ma_high + 1.2 * ATR14
```

之间。

这一步用于避免把远离均线束后的单边趋势误识别为密集。

---

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

---

## 4. 密集区结束后的方向选择

确认密集区后，策略记录：

```text
cluster_zone_high = 密集区上沿
cluster_zone_low  = 密集区下沿
```

密集区结束后，最多等待：

```python
cluster_breakout_window = 96
```

根 K 线寻找突破。

每个密集区最多产生一次方向突破记录。  
但突破不再只有一种严格定义，而是拆分为：

```text
强突破
弱突破
```

核心思想：

```text
强突破：价格已经明显离开密集区，可以直接确认方向。
弱突破：价格刚刚挤出密集区，但趋势确认不足，不直接开仓，只等待后续回踩或反抽确认。
```

---

## 5. 方向评分机制

原策略中要求完整均线排列：

```text
多头：fast_mid > mid_mid > slow_mid
空头：fast_mid < mid_mid < slow_mid
```

该条件对 BTC / ETH 的 1h 级别较为严格。  
很多行情中，价格会先突破平台，随后短均线带动中均线，最后长均线才跟上。

因此，本版策略将“完整排列”改成“方向评分”。

---

### 5.1 多头方向评分

多头方向得分 `long_direction_score` 满分为 5 分：

```text
1. fast_mid > mid_mid，加 1 分
2. mid_mid > slow_mid，加 1 分
3. fast_mid 当前斜率 > 0，加 1 分
4. close > slow_mid，加 1 分
5. close > ma_high，加 1 分
```

其中 `fast_mid` 斜率可以定义为：

```text
fast_mid_slope = fast_mid / fast_mid.shift(3) - 1
```

若：

```text
fast_mid_slope > 0
```

则认为短期均线组开始向上。

---

### 5.2 空头方向评分

空头方向得分 `short_direction_score` 满分为 5 分：

```text
1. fast_mid < mid_mid，加 1 分
2. mid_mid < slow_mid，加 1 分
3. fast_mid 当前斜率 < 0，加 1 分
4. close < slow_mid，加 1 分
5. close < ma_low，加 1 分
```

其中：

```text
fast_mid_slope = fast_mid / fast_mid.shift(3) - 1
```

若：

```text
fast_mid_slope < 0
```

则认为短期均线组开始向下。

---

### 5.3 评分阈值

建议参数：

```python
strong_breakout_score_threshold = 4
weak_breakout_score_threshold = 3
```

含义：

```text
强突破：方向评分至少 4 分
弱突破：方向评分至少 3 分
```

这样既保留方向过滤，又避免因为完整均线排列尚未形成而错过早期突破。

---

## 6. 多头突破定义

### 6.1 多头强突破

满足以下条件时，视为多头强突破：

```text
1. close > cluster_zone_high + strong_breakout_buffer
2. close > ma_high
3. 当前 K 线不是明显阴线
4. long_direction_score >= 4
```

其中突破缓冲：

```text
strong_breakout_buffer = max(close * 0.08%, 0.10 * ATR14)
```

“当前 K 线不是明显阴线”可以定义为：

```text
close >= open * 0.998
```

这意味着：

- 阳线一定满足；
- 小阴线也可以接受；
- 明显阴线不接受。

对应建议参数：

```python
strong_breakout_pct_buffer = 0.0008
strong_breakout_atr_buffer = 0.10
```

多头强突破出现后，可以选择两种处理方式：

```text
方案 A：直接开多；
方案 B：只记录强突破状态，等待第一次回踩确认后开多。
```

如果希望交易更少、更稳，使用方案 B。  
如果希望增加交易次数，使用方案 A。

---

### 6.2 多头弱突破

满足以下条件时，视为多头弱突破：

```text
1. close > cluster_zone_high
2. close >= ma_high - 0.3 * ATR14
3. long_direction_score >= 3
4. 不要求当前 K 线必须为阳线
5. 不要求 fast_mid > mid_mid > slow_mid 完整多头排列
```

多头弱突破不直接开仓，只记录突破状态：

```text
weak_breakout_long = True
weak_breakout_body_low = min(open, close)
weak_breakout_high = high
weak_breakout_cluster_high = cluster_zone_high
```

随后等待第一次回踩确认。

对应建议参数：

```python
weak_breakout_ma_tolerance_atr = 0.30
```

---

## 7. 空头突破定义

### 7.1 空头强突破

满足以下条件时，视为空头强突破：

```text
1. close < cluster_zone_low - strong_breakout_buffer
2. close < ma_low
3. 当前 K 线不是明显阳线
4. short_direction_score >= 4
```

其中突破缓冲：

```text
strong_breakout_buffer = max(close * 0.08%, 0.10 * ATR14)
```

“当前 K 线不是明显阳线”可以定义为：

```text
close <= open * 1.002
```

这意味着：

- 阴线一定满足；
- 小阳线也可以接受；
- 明显阳线不接受。

空头强突破出现后，可以选择：

```text
方案 A：直接开空；
方案 B：只记录强突破状态，等待第一次反抽确认后开空。
```

---

### 7.2 空头弱突破

满足以下条件时，视为空头弱突破：

```text
1. close < cluster_zone_low
2. close <= ma_low + 0.3 * ATR14
3. short_direction_score >= 3
4. 不要求当前 K 线必须为阴线
5. 不要求 fast_mid < mid_mid < slow_mid 完整空头排列
```

空头弱突破不直接开仓，只记录突破状态：

```text
weak_breakout_short = True
weak_breakout_body_high = max(open, close)
weak_breakout_low = low
weak_breakout_cluster_low = cluster_zone_low
```

随后等待第一次反抽确认。

---

## 8. 删除“前一根必须尚未突破”的硬条件

原策略中存在类似条件：

```text
前一根 K 线尚未有效站上密集区上沿
```

或：

```text
前一根 K 线尚未有效跌破密集区下沿
```

该条件容易漏掉 BTC / ETH 中常见的慢突破走势。

例如：

```text
第一根 K 线轻微站上平台，但不满足强突破；
第二根 K 线继续站稳，但由于前一根已经站上平台，被过滤；
第三根 K 线真正走强，但策略已经错过突破识别。
```

本版建议删除该硬条件，改为状态机逻辑：

```text
如果当前 cluster 尚未记录过突破，
并且当前 K 线满足强突破或弱突破，
则记录该 cluster 已经发生突破。
```

也就是说，每个密集区只允许记录一次突破，但不要求“前一根必须没有突破”。

伪代码：

```python
if cluster_active is False and cluster_has_breakout is False:
    if long_strong_breakout or long_weak_breakout:
        cluster_has_breakout = True
        breakout_direction = "long"
        breakout_type = "strong" if long_strong_breakout else "weak"

    elif short_strong_breakout or short_weak_breakout:
        cluster_has_breakout = True
        breakout_direction = "short"
        breakout_type = "strong" if short_strong_breakout else "weak"
```

---

## 9. 突破后的第一次回踩开仓

回踩信号不能凭空出现，必须发生在一次有效密集突破之后。

突破后最多等待：

```python
pullback_window = 96
```

根 K 线寻找第一次回踩或反抽。

---

### 9.1 多头强突破后的处理

若多头强突破选择直接开仓，则入场点为强突破 K 线收盘附近。

记录止损参考线：

```text
pullback_stop_long_line = min(open, close)
```

如果选择等待回踩，则后续出现第一根真正回踩 K 线时，如果：

```text
low >= pullback_stop_long_line
```

则开多。

当前对“第一根真正回踩 K 线”的识别为满足以下任意一个：

```text
1. 当前收盘价低于前一根收盘价
2. 当前最低价低于前一根最低价
3. 当前 K 线为阴线
```

不要求回踩 5 线，也不要求回踩 K 线必须收阳。  
核心只看：

```text
第一次回踩是否守住突破 K 线实体下沿。
```

---

### 9.2 多头弱突破后的回踩确认

多头弱突破不直接开仓。

弱突破后，等待第一次回踩。  
如果回踩满足以下任意一种确认方式，则开多。

#### 方式 A：守住突破 K 线实体下沿

```text
low >= weak_breakout_body_low - body_line_tolerance
```

#### 方式 B：守住密集区上沿

```text
close >= cluster_zone_high - cluster_line_tolerance
```

推荐使用方式 A 和方式 B 的组合：

```text
满足以下任意一个即可开多：

1. low >= weak_breakout_body_low - body_line_tolerance
2. close >= cluster_zone_high - cluster_line_tolerance
```

对应建议参数：

```python
body_line_tolerance = 0.001 * close
cluster_line_tolerance = 0.15 * ATR14
```

这样可以允许轻微刺破，但不能明显跌回密集区内部。

---

### 9.3 空头强突破后的处理

若空头强突破选择直接开仓，则入场点为强突破 K 线收盘附近。

记录止损参考线：

```text
pullback_stop_short_line = max(open, close)
```

如果选择等待反抽，则后续出现第一根真正反抽 K 线时，如果：

```text
high <= pullback_stop_short_line
```

则开空。

当前对“第一根真正反抽 K 线”的识别为满足以下任意一个：

```text
1. 当前收盘价高于前一根收盘价
2. 当前最高价高于前一根最高价
3. 当前 K 线为阳线
```

不要求反抽 5 线，也不要求反抽 K 线必须收阴。  
核心只看：

```text
第一次反抽是否被突破 K 线实体上沿压住。
```

---

### 9.4 空头弱突破后的反抽确认

空头弱突破不直接开仓。

弱突破后，等待第一次反抽。  
如果反抽满足以下任意一种确认方式，则开空。

#### 方式 A：被突破 K 线实体上沿压住

```text
high <= weak_breakout_body_high + body_line_tolerance
```

#### 方式 B：被密集区下沿压住

```text
close <= cluster_zone_low + cluster_line_tolerance
```

推荐使用方式 A 和方式 B 的组合：

```text
满足以下任意一个即可开空：

1. high <= weak_breakout_body_high + body_line_tolerance
2. close <= cluster_zone_low + cluster_line_tolerance
```

对应建议参数：

```python
body_line_tolerance = 0.001 * close
cluster_line_tolerance = 0.15 * ATR14
```

---

## 10. 止损

策略按入场类型使用不同止损。

---

### 10.1 强突破直接开仓单

如果强突破直接开仓，多单止损使用：

```text
stop_long = min(
    breakout_body_low - 0.15 * ATR14,
    cluster_zone_low - 0.15 * ATR14
)
```

空单止损使用：

```text
stop_short = max(
    breakout_body_high + 0.15 * ATR14,
    cluster_zone_high + 0.15 * ATR14
)
```

这样可以同时参考：

1. 突破 K 线实体；
2. 原密集区边界。

---

### 10.2 强突破后回踩开仓单

多单止损：

```text
stop_long = pullback_stop_long_line - 0.15 * ATR14
```

空单止损：

```text
stop_short = pullback_stop_short_line + 0.15 * ATR14
```

---

### 10.3 弱突破后回踩开仓单

多单止损优先使用：

```text
stop_long = min(
    weak_breakout_body_low - 0.15 * ATR14,
    cluster_zone_high - 0.30 * ATR14
)
```

空单止损优先使用：

```text
stop_short = max(
    weak_breakout_body_high + 0.15 * ATR14,
    cluster_zone_low + 0.30 * ATR14
)
```

弱突破本身不够强，因此止损不宜过紧。  
如果止损过紧，很容易被正常回踩或反抽扫掉。

---

### 10.4 密集区失效止损

如果是直接基于密集区突破入场，也可以保留原密集区失效止损。

多单止损：

```text
连续两根 K 线有效跌破原密集区下沿
```

有效跌破加入缓冲：

```text
close < cluster_zone_low - 0.15 * ATR14
```

空单止损：

```text
连续两根 K 线有效突破原密集区上沿
```

有效突破加入缓冲：

```text
close > cluster_zone_high + 0.15 * ATR14
```

---

### 10.5 灾难止损

策略层灾难止损：

```python
stoploss = -0.03
```

这是账户维度 `-3%`，等效真实 `100U` 保证金视角 `-300%`。

---

## 11. 止盈

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

- 多单看前高；
- 空单看前低。

止盈选择：

```text
1. 原则上盈亏比不能低于 2:1；
2. 如果前高 / 前低位于 2R 到 3R 之间，优先使用该结构位；
3. 如果结构位超过 3R，使用 3R；
4. 如果结构位不足 2R 或不可用，使用 2R。
```

---

## 12. 大幅盈利移动止盈

真实保证金视角盈利达到 `+200%` 时，启动移动止盈。

在当前等效回测中：

```text
账户盈利 +2% ≈ 保证金盈利 +200%
```

启动后记录该单历史最大浮盈。

如果从最高浮盈回吐 `50%`，立即止盈。

示例：

```text
最高浮盈 +200%，回落到 +100%，止盈
最高浮盈 +300%，回落到 +150%，止盈
最高浮盈 +500%，回落到 +250%，止盈
```

---

## 13. 推荐参数汇总

### 13.1 密集区参数

```python
ma_cluster_width_threshold = 0.025

ma_flat_slope_lookback = 6
ma_flat_slope_threshold = 0.012

ma_group_contract_window = 12
ma_group_contract_ratio = 0.92

sideways_lookback = 12
sideways_range_atr_max = 3.2
sideways_range_pct_max = 0.045
```

---

### 13.2 突破参数

```python
cluster_breakout_window = 96
pullback_window = 96

strong_breakout_pct_buffer = 0.0008
strong_breakout_atr_buffer = 0.10

weak_breakout_ma_tolerance_atr = 0.30

strong_breakout_score_threshold = 4
weak_breakout_score_threshold = 3
```

---

### 13.3 回踩与反抽容忍参数

```python
body_line_tolerance_pct = 0.001
cluster_line_tolerance_atr = 0.15
```

含义：

```text
body_line_tolerance = close * 0.001
cluster_line_tolerance = ATR14 * 0.15
```

---

### 13.4 止损参数

```python
body_stop_atr_buffer = 0.15
cluster_stop_atr_buffer = 0.30
invalid_break_atr_buffer = 0.15
```

---

## 14. 建议的策略执行顺序

完整执行流程如下：

```text
1. 计算六条均线：
   MA5 / EMA5 / MA10 / EMA10 / MA30 / EMA30

2. 计算均线束：
   ma_high / ma_low / ma_width

3. 计算三组中值：
   fast_mid / mid_mid / slow_mid

4. 判断均线密集候选：
   六线粘合
   相对收敛或近期收缩
   六线走平
   三组距离收缩
   价格横盘
   价格靠近均线束

5. 多根确认：
   最近 6 根中至少 4 根为密集候选

6. 记录密集区：
   cluster_zone_high
   cluster_zone_low

7. 密集区结束后等待突破：
   最多等待 96 根 K 线

8. 计算方向评分：
   long_direction_score
   short_direction_score

9. 判断强突破或弱突破：
   多头强突破
   多头弱突破
   空头强突破
   空头弱突破

10. 如果是强突破：
    可以直接开仓；
    或者记录强突破，等待第一次回踩 / 反抽。

11. 如果是弱突破：
    不直接开仓；
    只记录突破状态，等待第一次回踩 / 反抽。

12. 回踩或反抽确认后入场。

13. 根据入场类型设置止损。

14. 根据 R 倍数和前高 / 前低设置止盈。

15. 大幅盈利后启动移动止盈。
```

---

## 15. 和旧版本相比的核心变化

| 模块 | 旧版本 | 新版本 |
|---|---|---|
| 密集区识别 | 已经较接近人工观察 | 基本保持不变 |
| 突破定义 | 单一严格突破 | 强突破 + 弱突破 |
| 均线排列 | 必须完整多头 / 空头排列 | 改为方向评分 |
| 前一根突破限制 | 要求前一根尚未有效突破 | 删除，改为 cluster 状态机 |
| 弱突破处理 | 没有弱突破 | 弱突破只记录，不直接开仓 |
| 回踩确认 | 只看第一次回踩守实体线 | 保留实体线，同时允许参考密集区边界 |
| 主要目标 | 避免假突破 | 在可控范围内增加交易机会 |

---

## 16. 当前建议优先级

如果要逐步修改代码，建议按以下顺序进行。

### 第一优先级：删除完整均线排列硬条件

将：

```text
fast_mid > mid_mid > slow_mid
```

替换为：

```text
long_direction_score >= 4
```

将：

```text
fast_mid < mid_mid < slow_mid
```

替换为：

```text
short_direction_score >= 4
```

这是最关键的一步。

---

### 第二优先级：增加弱突破

新增：

```text
long_weak_breakout
short_weak_breakout
```

弱突破不直接交易，只进入等待回踩 / 反抽状态。

---

### 第三优先级：删除“前一根未突破”限制

将突破判断改成：

```text
每个 cluster 只记录一次突破
```

而不是：

```text
必须当前突破且上一根未突破
```

---

### 第四优先级：强突破是否直接开仓

如果交易仍然太少，可以允许强突破直接开仓。  
如果假突破太多，则强突破也等待回踩确认。

推荐先采用：

```text
强突破：等待回踩确认
弱突破：等待回踩确认
```

如果交易数量仍然不足，再改成：

```text
强突破：直接开仓
弱突破：等待回踩确认
```

---

## 17. 需要重点观察的回测指标

修改后重点观察：

```text
1. cluster 数量是否基本稳定；
2. strong_breakout 数量是否增加；
3. weak_breakout 数量是否明显增加；
4. weak_breakout 中有多少最终成功回踩入场；
5. BTC 是否开始产生交易；
6. ETH 交易数是否从 1 笔增加到合理数量；
7. 胜率是否下降过多；
8. Profit Factor 是否改善；
9. 最大回撤是否可控；
10. 假突破止损是否明显增多。
```

不要只看交易数量。  
交易数量增加后，如果假突破显著增多，需要优先调整：

```text
weak_breakout_score_threshold
weak_breakout_ma_tolerance_atr
cluster_line_tolerance_atr
```

---

## 18. 最终策略思想

本策略的核心不是追求“极窄均线压缩”，而是寻找：

```text
趋势暂缓
均线粘合
价格横盘
方向选择
突破后确认
```

因此，密集区只负责找到“可能要选择方向的位置”。  
真正决定是否交易的是突破和回踩确认。

最终逻辑可以概括为：

```text
用均线密集区寻找蓄势位置；
用强弱突破判断方向选择；
用第一次回踩或反抽过滤假突破；
用实体线和密集区边界控制止损；
用 2R / 3R 和结构位完成止盈。
```

相比旧版本，本版不会盲目放宽密集区，而是把过于苛刻的突破条件拆成两层。  
这样更符合 BTC / ETH 中常见的“慢突破、后排列、再加速”的走势结构。
