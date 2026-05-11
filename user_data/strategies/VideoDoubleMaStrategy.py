from __future__ import annotations

import pandas as pd
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class VideoDoubleMaStrategy(IStrategy):
    """按 vdCdg4MdwBs 视频整理的“双均线/双线交易系统”保守版本。

    视频核心不是常见的 50/200 双均线，而是：
    - 3 条 MA：20、60、120
    - 3 条 EMA：20、60、120
    - 重点观察“均线密集”之后的方向选择，以及突破后的第一次回踩 20 线不破。

    当前实现为了能在现货 Freqtrade 里先跑通，只实现做多逻辑。
    视频中也讲了做空、合约、杠杆和逐仓，但这些需要 futures 配置，先不混进现货回测。
    """

    INTERFACE_VERSION = 3

    timeframe = "4h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 180

    # 视频讲的是按结构止损和高盈亏比出场。
    # Freqtrade 的 minimal_roi 是静态规则，不能完美表达“按入场结构计算 1:3/1:5”。
    # 这里保留一个宽松的灾难止损和很高的 ROI，让主要出场由均线结构决定。
    stoploss = -0.08
    minimal_roi = {
        "0": 0.24,
        "240": 0.12,
        "480": 0.0,
    }

    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # 程序化阈值：视频用肉眼判断“均线缠在一起”，代码必须给出数值定义。
    # cluster_width = (六条均线最高值 - 最低值) / close。
    ma_cluster_width_threshold = 0.03
    cluster_lookback = 72
    pullback_window = 72
    breakout_buffer = 0.001
    pullback_touch_tolerance = 0.003

    @staticmethod
    def _sma(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window, min_periods=window).mean()

    @staticmethod
    def _ema(series: pd.Series, window: int) -> pd.Series:
        return series.ewm(span=window, adjust=False, min_periods=window).mean()

    def _mark_first_pullback_after_breakout(self, dataframe: DataFrame) -> pd.Series:
        """标记“均线密集突破后，第一次回踩 20 线不破”。

        这是视频里的第二类开仓方法。实现时只向前滚动状态，不读取未来 K 线。
        """

        waiting_for_pullback = False
        bars_after_breakout = 0
        signals: list[bool] = []

        breakout_up = dataframe["cluster_breakout_up"].fillna(False).to_numpy()
        pullback_ok = dataframe["pullback_20_no_break"].fillna(False).to_numpy()
        close = dataframe["close"].to_numpy()
        ma_low = dataframe["ma_low"].to_numpy()

        for i in range(len(dataframe)):
            signal = False

            if breakout_up[i]:
                waiting_for_pullback = True
                bars_after_breakout = 0
            elif waiting_for_pullback:
                bars_after_breakout += 1

            if waiting_for_pullback and bars_after_breakout > 0 and pullback_ok[i]:
                signal = True
                waiting_for_pullback = False

            # 价格重新跌回整组均线下方，说明这次突破失败。
            if waiting_for_pullback and (bars_after_breakout > self.pullback_window or close[i] < ma_low[i]):
                waiting_for_pullback = False

            signals.append(signal)

        return pd.Series(signals, index=dataframe.index)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 视频明确规则：MA/EMA 各 20、60、120，共六条均线。
        dataframe["ma_20"] = self._sma(dataframe["close"], 20)
        dataframe["ma_60"] = self._sma(dataframe["close"], 60)
        dataframe["ma_120"] = self._sma(dataframe["close"], 120)
        dataframe["ema_20"] = self._ema(dataframe["close"], 20)
        dataframe["ema_60"] = self._ema(dataframe["close"], 60)
        dataframe["ema_120"] = self._ema(dataframe["close"], 120)

        ma_cols = ["ma_20", "ma_60", "ma_120", "ema_20", "ema_60", "ema_120"]
        dataframe["ma_high"] = dataframe[ma_cols].max(axis=1)
        dataframe["ma_low"] = dataframe[ma_cols].min(axis=1)
        dataframe["ma_width"] = (dataframe["ma_high"] - dataframe["ma_low"]) / dataframe["close"]

        # 视频概念：均线密集 = 六条均线缠在一起，分不清谁上谁下。
        dataframe["ma_cluster"] = dataframe["ma_width"] <= self.ma_cluster_width_threshold
        dataframe["recent_cluster"] = (
            dataframe["ma_cluster"].rolling(self.cluster_lookback, min_periods=1).max().fillna(False).astype(bool)
        )

        # 视频概念：均线发散且向上 = 20 在上、60 在中、120 在下，价格站在均线上方。
        dataframe["ma_20_mid"] = (dataframe["ma_20"] + dataframe["ema_20"]) / 2
        dataframe["ma_60_mid"] = (dataframe["ma_60"] + dataframe["ema_60"]) / 2
        dataframe["ma_120_mid"] = (dataframe["ma_120"] + dataframe["ema_120"]) / 2
        dataframe["bullish_ma_order"] = (
            (dataframe["ma_20_mid"] > dataframe["ma_60_mid"])
            & (dataframe["ma_60_mid"] > dataframe["ma_120_mid"])
            & (dataframe["close"] > dataframe["ma_high"])
        )

        # 第一类入场：均线密集后，价格向上有效站上整组均线。
        dataframe["cluster_breakout_up"] = (
            dataframe["recent_cluster"]
            & (dataframe["close"] > dataframe["ma_high"] * (1 + self.breakout_buffer))
            & (dataframe["close"].shift(1) <= dataframe["ma_high"].shift(1) * (1 + self.breakout_buffer))
        )

        # 第二类入场：均线密集突破后，第一次回踩 20 线不破。
        # 同时存在 MA20 和 EMA20，所以这里把两条 20 线视为一组支撑带。
        dataframe["ma20_band_high"] = dataframe[["ma_20", "ema_20"]].max(axis=1)
        dataframe["ma20_band_low"] = dataframe[["ma_20", "ema_20"]].min(axis=1)
        dataframe["pullback_20_no_break"] = (
            dataframe["bullish_ma_order"]
            & (dataframe["low"] <= dataframe["ma20_band_high"] * (1 + self.pullback_touch_tolerance))
            & (dataframe["close"] >= dataframe["ma20_band_low"])
        )
        dataframe["first_pullback_long"] = self._mark_first_pullback_after_breakout(dataframe)

        # 视频止损思想：用什么开仓，就用什么止损；回踩 20 线开仓，跌破 20 线止损。
        # “有效跌破”这里用连续两根收盘跌破 20 线支撑带近似。
        dataframe["effective_break_20"] = (
            (dataframe["close"] < dataframe["ma20_band_low"])
            & (dataframe["close"].shift(1) < dataframe["ma20_band_low"].shift(1))
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & dataframe["cluster_breakout_up"]
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "cluster_breakout_up")

        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & dataframe["first_pullback_long"]
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "first_pullback_20_hold")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & (
                    dataframe["effective_break_20"]
                    | (dataframe["close"] < dataframe["ma_low"])
                )
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "structure_stop")

        return dataframe
