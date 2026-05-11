from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class LlmFactorBtcEthStrategy(IStrategy):
    """Fixed BTC/ETH factor strategy for Freqtrade backtesting.

    LLM-generated ideas must be evaluated offline first. This strategy does not
    call any LLM during backtesting, dry-run, or live execution.
    """

    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 600

    minimal_roi = {
        "0": 0.08,
        "96": 0.03,
        "192": 0.0,
    }

    stoploss = -0.08

    trailing_stop = True
    trailing_stop_positive = 0.025
    trailing_stop_positive_offset = 0.06
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    @staticmethod
    def _sma(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window, min_periods=window).mean()

    @staticmethod
    def _ema(series: pd.Series, window: int) -> pd.Series:
        return series.ewm(span=window, adjust=False, min_periods=window).mean()

    @staticmethod
    def _zscore(series: pd.Series, window: int) -> pd.Series:
        mean = series.rolling(window, min_periods=window).mean()
        std = series.rolling(window, min_periods=window).std(ddof=0)
        return (series - mean) / std.replace(0, np.nan)

    @staticmethod
    def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
        delta = close.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        avg_gain = up.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
        avg_loss = down.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(dataframe: DataFrame, window: int = 14) -> pd.Series:
        previous_close = dataframe["close"].shift(1)
        true_range = pd.concat(
            [
                dataframe["high"] - dataframe["low"],
                (dataframe["high"] - previous_close).abs(),
                (dataframe["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_12"] = self._ema(dataframe["close"], 12)
        dataframe["ema_48"] = self._ema(dataframe["close"], 48)
        dataframe["ema_200"] = self._ema(dataframe["close"], 200)
        dataframe["rsi_14"] = self._rsi(dataframe["close"], 14)
        dataframe["volume_sma_20"] = self._sma(dataframe["volume"], 20)

        dataframe["atr_14"] = self._atr(dataframe, 14)
        dataframe["atr_pct"] = dataframe["atr_14"] / dataframe["close"]
        dataframe["atr_pct_hi"] = dataframe["atr_pct"].rolling(120, min_periods=120).quantile(0.90)

        dataframe["momentum_24"] = dataframe["close"].pct_change(24)
        dataframe["volume_ratio_20"] = dataframe["volume"] / dataframe["volume_sma_20"]
        dataframe["factor_mom_vol"] = self._zscore(dataframe["momentum_24"], 120) * self._zscore(
            dataframe["volume_ratio_20"], 120
        )

        trend_raw = dataframe["ema_12"] / dataframe["ema_48"] - 1
        vol_penalty = self._zscore(dataframe["atr_pct"], 120).abs() + 1
        dataframe["factor_trend_quality"] = self._zscore(trend_raw, 120) / vol_penalty

        breakout_raw = dataframe["close"] / dataframe["close"].rolling(48, min_periods=48).max() - 1
        dataframe["factor_breakout"] = self._zscore(breakout_raw, 120) * self._zscore(dataframe["volume"], 120)

        dataframe["factor_score"] = (
            0.45 * dataframe["factor_mom_vol"]
            + 0.35 * dataframe["factor_trend_quality"]
            + 0.20 * dataframe["factor_breakout"]
        )
        dataframe["factor_score_q70"] = dataframe["factor_score"].rolling(120, min_periods=120).quantile(0.70)

        dataframe.replace([np.inf, -np.inf], np.nan, inplace=True)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & (dataframe["volume"] > dataframe["volume_sma_20"])
                & (dataframe["close"] > dataframe["ema_200"])
                & (dataframe["ema_12"] > dataframe["ema_48"])
                & (dataframe["rsi_14"].between(45, 72))
                & (dataframe["atr_pct"] < dataframe["atr_pct_hi"])
                & (dataframe["factor_score"] > dataframe["factor_score_q70"])
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "llm_factor_confluence")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & (
                    (dataframe["close"] < dataframe["ema_48"])
                    | (dataframe["ema_12"] < dataframe["ema_48"])
                    | (dataframe["factor_score"] < 0)
                    | (dataframe["rsi_14"] > 82)
                )
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "factor_exit")

        return dataframe
