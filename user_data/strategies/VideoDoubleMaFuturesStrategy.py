from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
from freqtrade.strategy import IStrategy, merge_informative_pair, stoploss_from_absolute
from pandas import DataFrame


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class VideoDoubleMaFuturesStrategy(IStrategy):
    """Gate USDT 永续合约版：视频六均线策略的多空实现。

    视频核心规则：
    - 3 条 MA：5、10、30
    - 3 条 EMA：5、10、30
    - 均线密集后等待方向选择。
    - 方向突破后，重点观察第一次回踩/反抽 5 线。

    本策略使用 1h 作为主操作周期，允许做多和做空。
    回测采用“名义仓位等效法”：真实意图是 100U 保证金 * 100x = 10000U 名义仓位，
    且账户有 10000U 作为全仓风险缓冲。由于 Freqtrade 2026.4 不支持 Gate cross futures
    回测，这里用 10000U stake + 1x leverage 模拟相同名义仓位和接近 1x 的账户有效杠杆。
    """

    INTERFACE_VERSION = 3

    timeframe = "1h"
    informative_timeframe = "4h"
    can_short = True
    process_only_new_candles = True
    # 递归分析显示 ma_width 在 499 根启动 K 线后基本收敛。
    startup_candle_count = 499

    target_notional_stake = _env_float("VDM_TARGET_STAKE", 10000.0)
    target_leverage = _env_float("VDM_TARGET_LEVERAGE", 2.0)

    # 等效账户杠杆默认 2x：10000U 保证金 * 2x = 20000U 名义仓位。
    # 硬止损随等效杠杆放宽，避免在结构止损前被全局 stoploss 截断。
    stoploss = _env_float("VDM_GLOBAL_STOPLOSS", -0.06)

    # 止盈由 custom_exit 按入场止损点动态计算，这里设置成极高值，避免全局 ROI 表提前接管。
    minimal_roi = {
        "0": 1000.0,
    }

    trailing_stop = False
    use_custom_stoploss = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # 5/10/30 六均线密集必须像人工红框一样：走平、粘合、组距收缩、价格横盘。
    ma_cluster_width_threshold = 0.025
    ma_cluster_quantile_window = 180
    ma_cluster_quantile = 0.55
    ma_cluster_compression_window = 24
    ma_cluster_recent_compression_ratio = 0.92
    ma_flat_slope_lookback = 6
    ma_flat_slope_threshold = 0.012
    ma_group_contract_window = 12
    ma_group_contract_ratio = 0.92
    sideways_lookback = 12
    sideways_range_atr_max = 3.2
    sideways_range_pct_max = 0.045
    cluster_price_atr_tolerance = 1.2
    cluster_confirm_window = 6
    cluster_confirm_min_bars = 4
    cluster_breakout_window = 96
    pullback_window = 96
    direction_slope_lookback = 3
    strong_breakout_score_threshold = 4
    weak_breakout_score_threshold = 3
    strong_breakout_pct_buffer = 0.0008
    strong_breakout_atr_buffer = 0.10
    weak_breakout_ma_tolerance_atr = 0.30
    body_line_tolerance_pct = 0.001
    cluster_line_tolerance_atr = 0.15
    pullback_reclaim_window = _env_int("VDM_PULLBACK_RECLAIM_WINDOW", 3)
    pullback_confirm_score_threshold = _env_int("VDM_PULLBACK_SCORE", 3)
    pullback_confirm_zone_atr_buffer = _env_float("VDM_ZONE_ATR_BUFFER", 0.05)
    pullback_confirm_zone_pct_buffer = _env_float("VDM_ZONE_PCT_BUFFER", 0.0025)
    pullback_confirm_body_pct_min = _env_float("VDM_BODY_PCT_MIN", 0.001)
    trade_strong_breakouts = _env_bool("VDM_TRADE_STRONG", True)
    trade_weak_breakouts = _env_bool("VDM_TRADE_WEAK", True)
    body_stop_atr_buffer = _env_float("VDM_BODY_STOP_ATR_BUFFER", 0.15)
    cluster_stop_atr_buffer = _env_float("VDM_CLUSTER_STOP_ATR_BUFFER", 0.30)
    use_wide_cluster_stop_for_weak = _env_bool("VDM_USE_WIDE_CLUSTER_STOP", False)
    invalid_break_atr_buffer = 0.15
    stop_atr_buffer = 0.15
    pullback_touch_tolerance = 0.002
    swing_lookback = _env_int("VDM_SWING_LOOKBACK", 120)
    pivot_left_bars = _env_int("VDM_PIVOT_LEFT", 8)
    pivot_right_bars = _env_int("VDM_PIVOT_RIGHT", 4)
    use_pivot_structure = _env_bool("VDM_USE_PIVOT_STRUCTURE", True)
    swing_stop_policy = _env_int("VDM_SWING_STOP_POLICY", 1)
    swing_stop_atr_buffer = _env_float("VDM_SWING_STOP_ATR_BUFFER", 0.10)
    swing_stop_min_risk_pct = _env_float("VDM_SWING_STOP_MIN_RISK_PCT", 0.002)
    swing_stop_max_risk_pct = _env_float("VDM_SWING_STOP_MAX_RISK_PCT", 0.028)
    risk_reward_min = _env_float("VDM_RR_MIN", 2.3)
    risk_reward_preferred = _env_float("VDM_RR_PREF", 3.5)
    structure_target_max_rr = _env_float("VDM_STRUCTURE_TARGET_MAX_RR", 5.0)
    trend_structure_target_max_rr = _env_float("VDM_TREND_TARGET_MAX_RR", 7.0)
    use_htf_context = _env_bool("VDM_USE_HTF_CONTEXT", True)
    use_htf_filter = _env_bool("VDM_USE_HTF_FILTER", True)
    htf_score_min = _env_int("VDM_HTF_SCORE_MIN", 3)
    htf_trend_score_min = _env_int("VDM_HTF_TREND_SCORE_MIN", 4)
    htf_slope_min = _env_float("VDM_HTF_SLOPE_MIN", 0.0)
    # 0 = 周末正常开仓；1 = 周末保守开仓，固定小止盈/密集框止损；2 = 周末不新开仓。
    weekend_entry_mode = _env_int("VDM_WEEKEND_MODE", 0)
    weekend_profit_target = _env_float("VDM_WEEKEND_PROFIT_TARGET", 0.008)
    weekend_stop_atr_buffer = _env_float("VDM_WEEKEND_STOP_ATR_BUFFER", 0.05)
    # 额外的 1-2 根 K 假突破早退默认关闭；计划结构止损已由 custom_stoploss 提前执行。
    early_fail_window = _env_int("VDM_EARLY_FAIL_WINDOW", 0)
    early_fail_atr_buffer = _env_float("VDM_EARLY_FAIL_ATR_BUFFER", 0.05)
    early_fail_max_profit = _env_float("VDM_EARLY_FAIL_MAX_PROFIT", 0.002)
    # 趋势不强时 +2% 后保护利润；趋势强时延后到 +5%，尽量吃到更大波段。
    large_profit_trailing_start = _env_float("VDM_TRAIL_START", 0.02)
    trend_profit_trailing_start = _env_float("VDM_TREND_TRAIL_START", 0.05)
    trail_normal_enabled = _env_bool("VDM_TRAIL_NORMAL", False)
    trail_trend_enabled = _env_bool("VDM_TRAIL_TREND", True)
    large_profit_retrace_ratio = _env_float("VDM_RETRACE_RATIO", 0.50)
    trend_profit_retrace_ratio = _env_float("VDM_TREND_RETRACE_RATIO", 0.60)

    plot_config = {
        "main_plot": {
            "ma_5": {"color": "#0891b2"},
            "ema_5": {"color": "#14b8a6"},
            "ma_10": {"color": "#facc15"},
            "ema_10": {"color": "#f59e0b"},
            "ma_30": {"color": "#7c3aed"},
            "ema_30": {"color": "#a855f7"},
        },
        "subplots": {
            "MA width": {
                "ma_width": {"color": "#64748b"},
            }
        },
    }

    def bot_start(self, **kwargs) -> None:
        self._trade_peak_profit: dict[str, float] = {}

    def informative_pairs(self):
        if not (self.use_htf_context or self.use_htf_filter):
            return []
        return [(pair, self.informative_timeframe) for pair in self.dp.current_whitelist()]

    @staticmethod
    def _sma(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window, min_periods=window).mean()

    @staticmethod
    def _ema(series: pd.Series, window: int) -> pd.Series:
        return series.ewm(span=window, adjust=False, min_periods=window).mean()

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        return max(1.0, min(self.target_leverage, max_leverage))

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        stake = min(self.target_notional_stake, max_stake)
        if min_stake is not None:
            stake = max(stake, min_stake)
        return stake

    def custom_stoploss(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float | None:
        """把人工策略里的结构止损价转换成真实止损。

        `custom_exit` 只能在 K 线收盘后判断结构失效，长实体假突破会让亏损变大。
        这里使用入场 K 线记录的突破实体线、密集区边界和前高/前低，提前挂出计划止损。
        """

        dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if dataframe.empty:
            return self.stoploss

        candles_until_now = self._candles_until(dataframe, current_time)
        if candles_until_now.empty:
            return self.stoploss

        entry_candle = self._entry_candle(candles_until_now, trade)
        if entry_candle is None:
            return self.stoploss

        entry_tag = getattr(trade, "enter_tag", None) or getattr(trade, "entry_tag", None) or ""
        is_short = bool(getattr(trade, "is_short", False))
        stop_rate = self._planned_stop_rate(entry_candle, entry_tag, is_short)
        if stop_rate is None:
            return self.stoploss

        leverage = float(getattr(trade, "leverage", self.target_leverage) or self.target_leverage)
        return stoploss_from_absolute(
            float(stop_rate),
            current_rate,
            is_short=is_short,
            leverage=leverage,
        )

    @staticmethod
    def _true_range(dataframe: DataFrame) -> pd.Series:
        prev_close = dataframe["close"].shift(1)
        ranges = pd.concat(
            [
                dataframe["high"] - dataframe["low"],
                (dataframe["high"] - prev_close).abs(),
                (dataframe["low"] - prev_close).abs(),
            ],
            axis=1,
        )
        return ranges.max(axis=1)

    def _mark_cluster_state(self, dataframe: DataFrame) -> DataFrame:
        zone_high: list[float] = []
        zone_low: list[float] = []
        breakout_up: list[bool] = []
        breakout_down: list[bool] = []
        strong_breakout_up: list[bool] = []
        weak_breakout_up: list[bool] = []
        strong_breakout_down: list[bool] = []
        weak_breakout_down: list[bool] = []
        breakout_type_up: list[str] = []
        breakout_type_down: list[str] = []

        in_cluster = False
        waiting_breakout = False
        bars_after_cluster = 0
        current_high = float("nan")
        current_low = float("nan")

        confirmed = dataframe["ma_cluster_confirmed"].fillna(False).to_numpy()
        ma_high = dataframe["ma_high"].to_numpy()
        ma_low = dataframe["ma_low"].to_numpy()
        close = dataframe["close"].to_numpy()
        open_ = dataframe["open"].to_numpy()
        atr = dataframe["atr_14"].fillna(0.0).to_numpy()
        long_score = dataframe["long_direction_score"].fillna(0).to_numpy()
        short_score = dataframe["short_direction_score"].fillna(0).to_numpy()

        for i in range(len(dataframe)):
            signal_up = False
            signal_down = False
            strong_up = False
            weak_up = False
            strong_down = False
            weak_down = False
            up_type = ""
            down_type = ""

            if confirmed[i]:
                if not in_cluster:
                    current_high = ma_high[i]
                    current_low = ma_low[i]
                else:
                    current_high = max(current_high, ma_high[i])
                    current_low = min(current_low, ma_low[i])

                in_cluster = True
                waiting_breakout = False
                bars_after_cluster = 0
            else:
                if in_cluster:
                    in_cluster = False
                    waiting_breakout = True
                    bars_after_cluster = 0
                elif waiting_breakout:
                    bars_after_cluster += 1

                if waiting_breakout and bars_after_cluster <= self.cluster_breakout_window:
                    strong_buffer = max(
                        close[i] * self.strong_breakout_pct_buffer,
                        atr[i] * self.strong_breakout_atr_buffer,
                    )
                    long_not_obvious_bear = close[i] >= open_[i] * 0.998
                    short_not_obvious_bull = close[i] <= open_[i] * 1.002

                    strong_up = (
                        close[i] > current_high + strong_buffer
                        and close[i] > ma_high[i]
                        and long_not_obvious_bear
                        and long_score[i] >= self.strong_breakout_score_threshold
                    )
                    weak_up = (
                        not strong_up
                        and close[i] > current_high
                        and close[i] >= ma_high[i] - atr[i] * self.weak_breakout_ma_tolerance_atr
                        and long_score[i] >= self.weak_breakout_score_threshold
                    )
                    strong_down = (
                        close[i] < current_low - strong_buffer
                        and close[i] < ma_low[i]
                        and short_not_obvious_bull
                        and short_score[i] >= self.strong_breakout_score_threshold
                    )
                    weak_down = (
                        not strong_down
                        and close[i] < current_low
                        and close[i] <= ma_low[i] + atr[i] * self.weak_breakout_ma_tolerance_atr
                        and short_score[i] >= self.weak_breakout_score_threshold
                    )

                    long_breakout = strong_up or weak_up
                    short_breakout = strong_down or weak_down
                    if long_breakout and short_breakout:
                        if long_score[i] > short_score[i]:
                            short_breakout = False
                            strong_down = False
                            weak_down = False
                        elif short_score[i] > long_score[i]:
                            long_breakout = False
                            strong_up = False
                            weak_up = False
                        else:
                            long_breakout = False
                            short_breakout = False
                            strong_up = False
                            weak_up = False
                            strong_down = False
                            weak_down = False

                    if long_breakout:
                        signal_up = True
                        up_type = "strong" if strong_up else "weak"
                    if short_breakout:
                        signal_down = True
                        down_type = "strong" if strong_down else "weak"

                    if signal_up or signal_down:
                        waiting_breakout = False

                if waiting_breakout and bars_after_cluster > self.cluster_breakout_window:
                    waiting_breakout = False

            zone_high.append(current_high)
            zone_low.append(current_low)
            breakout_up.append(signal_up)
            breakout_down.append(signal_down)
            strong_breakout_up.append(strong_up and signal_up)
            weak_breakout_up.append(weak_up and signal_up)
            strong_breakout_down.append(strong_down and signal_down)
            weak_breakout_down.append(weak_down and signal_down)
            breakout_type_up.append(up_type)
            breakout_type_down.append(down_type)

        dataframe["cluster_zone_high"] = zone_high
        dataframe["cluster_zone_low"] = zone_low
        dataframe["cluster_breakout_up"] = breakout_up
        dataframe["cluster_breakout_down"] = breakout_down
        dataframe["cluster_strong_breakout_up"] = strong_breakout_up
        dataframe["cluster_weak_breakout_up"] = weak_breakout_up
        dataframe["cluster_strong_breakout_down"] = strong_breakout_down
        dataframe["cluster_weak_breakout_down"] = weak_breakout_down
        dataframe["cluster_breakout_type_up"] = breakout_type_up
        dataframe["cluster_breakout_type_down"] = breakout_type_down
        return dataframe

    @staticmethod
    def _trade_key(pair: str, trade) -> str:
        trade_id = getattr(trade, "id", None)
        if trade_id is not None:
            return f"{pair}-{trade_id}"
        return f"{pair}-{getattr(trade, 'open_date_utc', '')}-{getattr(trade, 'open_rate', '')}"

    @staticmethod
    def _entry_candle(dataframe: DataFrame, trade):
        open_time = pd.Timestamp(trade.open_date_utc)
        if open_time.tzinfo is None:
            open_time = open_time.tz_localize("UTC")
        else:
            open_time = open_time.tz_convert("UTC")

        dates = pd.to_datetime(dataframe["date"], utc=True)
        candles = dataframe.loc[dates <= open_time]
        if candles.empty:
            return None
        return candles.iloc[-1]

    @staticmethod
    def _candles_until(dataframe: DataFrame, current_time: datetime) -> DataFrame:
        candle_time = pd.Timestamp(current_time)
        if candle_time.tzinfo is None:
            candle_time = candle_time.tz_localize("UTC")
        else:
            candle_time = candle_time.tz_convert("UTC")
        dates = pd.to_datetime(dataframe["date"], utc=True)
        return dataframe.loc[dates <= candle_time]

    def _planned_stop_rate(self, entry_candle: pd.Series, entry_tag: str, is_short: bool) -> float | None:
        atr = float(entry_candle.get("atr_14", 0.0))
        atr_buffer = atr * self.stop_atr_buffer

        if "cluster_breakout" in entry_tag:
            if is_short:
                stop_rate = entry_candle.get("cluster_zone_high", float("nan")) + atr_buffer
            else:
                stop_rate = entry_candle.get("cluster_zone_low", float("nan")) - atr_buffer
        elif "pullback" in entry_tag:
            if is_short:
                body_stop = entry_candle.get("pullback_stop_short_line", float("nan")) + atr * self.body_stop_atr_buffer
                if "weak" in entry_tag and self.use_wide_cluster_stop_for_weak:
                    cluster_stop = entry_candle.get("cluster_zone_low", float("nan")) + atr * self.cluster_stop_atr_buffer
                    stop_rate = max(body_stop, cluster_stop)
                else:
                    stop_rate = body_stop
            else:
                body_stop = entry_candle.get("pullback_stop_long_line", float("nan")) - atr * self.body_stop_atr_buffer
                if "weak" in entry_tag and self.use_wide_cluster_stop_for_weak:
                    cluster_stop = entry_candle.get("cluster_zone_high", float("nan")) - atr * self.cluster_stop_atr_buffer
                    stop_rate = min(body_stop, cluster_stop)
                else:
                    stop_rate = body_stop
            if pd.isna(stop_rate):
                if is_short:
                    stop_rate = entry_candle.get("fast_band_high", float("nan")) + atr_buffer
                else:
                    stop_rate = entry_candle.get("fast_band_low", float("nan")) - atr_buffer
        else:
            return None

        if pd.isna(stop_rate) or stop_rate <= 0:
            return None
        if self.weekend_entry_mode == 1 and bool(entry_candle.get("is_weekend", False)):
            if is_short:
                weekend_stop = entry_candle.get("cluster_zone_high", float("nan")) + atr * self.weekend_stop_atr_buffer
            else:
                weekend_stop = entry_candle.get("cluster_zone_low", float("nan")) - atr * self.weekend_stop_atr_buffer
            if pd.notna(weekend_stop) and weekend_stop > 0:
                return float(weekend_stop)
        stop_rate = self._structure_stop_rate(entry_candle, float(stop_rate), is_short)
        return float(stop_rate)

    def _structure_stop_rate(self, entry_candle: pd.Series, base_stop: float, is_short: bool) -> float:
        if not self.use_pivot_structure or self.swing_stop_policy <= 0:
            return base_stop

        entry_rate = float(entry_candle.get("close", 0.0))
        atr = float(entry_candle.get("atr_14", 0.0))
        if entry_rate <= 0 or atr <= 0:
            return base_stop

        if is_short:
            pivot = entry_candle.get("prev_pivot_high", float("nan"))
            candidate = pivot + atr * self.swing_stop_atr_buffer
            risk_pct = (candidate - entry_rate) / entry_rate
            candidate_is_wider = candidate > base_stop
        else:
            pivot = entry_candle.get("prev_pivot_low", float("nan"))
            candidate = pivot - atr * self.swing_stop_atr_buffer
            risk_pct = (entry_rate - candidate) / entry_rate
            candidate_is_wider = candidate < base_stop

        if pd.isna(candidate) or candidate <= 0:
            return base_stop
        if risk_pct < self.swing_stop_min_risk_pct or risk_pct > self.swing_stop_max_risk_pct:
            return base_stop

        if self.swing_stop_policy == 2 and not candidate_is_wider:
            return base_stop
        if self.swing_stop_policy == 3 and candidate_is_wider:
            return base_stop
        return float(candidate)

    def _take_profit_rate(self, entry_candle: pd.Series, entry_rate: float, stop_rate: float, is_short: bool) -> float | None:
        if self.weekend_entry_mode == 1 and bool(entry_candle.get("is_weekend", False)):
            if is_short:
                return float(entry_rate * (1 - self.weekend_profit_target))
            return float(entry_rate * (1 + self.weekend_profit_target))

        target_max_rr = self._target_max_rr(entry_candle, is_short)
        if is_short:
            risk = stop_rate - entry_rate
            if risk <= 0:
                return None
            target_2r = entry_rate - self.risk_reward_min * risk
            target_3r = entry_rate - self.risk_reward_preferred * risk
            target_max = entry_rate - target_max_rr * risk
            swing_target = self._structure_target(entry_candle, is_short)

            if pd.notna(swing_target) and target_max <= swing_target <= target_2r:
                return float(swing_target)
            if pd.notna(swing_target) and swing_target < target_max:
                return float(target_max)
            return float(target_2r)

        risk = entry_rate - stop_rate
        if risk <= 0:
            return None
        target_2r = entry_rate + self.risk_reward_min * risk
        target_3r = entry_rate + self.risk_reward_preferred * risk
        target_max = entry_rate + target_max_rr * risk
        swing_target = self._structure_target(entry_candle, is_short)

        if pd.notna(swing_target) and target_2r <= swing_target <= target_max:
            return float(swing_target)
        if pd.notna(swing_target) and swing_target > target_max:
            return float(target_max)
        return float(target_2r)

    def _target_max_rr(self, entry_candle: pd.Series, is_short: bool) -> float:
        return self.trend_structure_target_max_rr if self._is_strong_trend(entry_candle, is_short) else self.structure_target_max_rr

    def _trailing_start(self, entry_candle: pd.Series, is_short: bool) -> float:
        return self.trend_profit_trailing_start if self._is_strong_trend(entry_candle, is_short) else self.large_profit_trailing_start

    def _trailing_enabled(self, entry_candle: pd.Series, is_short: bool) -> bool:
        return self.trail_trend_enabled if self._is_strong_trend(entry_candle, is_short) else self.trail_normal_enabled

    def _trailing_retrace_ratio(self, entry_candle: pd.Series, is_short: bool) -> float:
        return self.trend_profit_retrace_ratio if self._is_strong_trend(entry_candle, is_short) else self.large_profit_retrace_ratio

    def _is_strong_trend(self, entry_candle: pd.Series, is_short: bool) -> bool:
        if is_short:
            score = entry_candle.get("short_direction_score_4h", float("nan"))
            local_score = entry_candle.get("short_direction_score", 0)
        else:
            score = entry_candle.get("long_direction_score_4h", float("nan"))
            local_score = entry_candle.get("long_direction_score", 0)
        if pd.isna(score):
            return False
        return score >= self.htf_trend_score_min and local_score >= self.strong_breakout_score_threshold

    def _early_false_breakout_exit(
        self,
        candles_until_now: DataFrame,
        entry_candle: pd.Series,
        trade,
        current_rate: float,
        current_profit: float,
        is_short: bool,
    ) -> str | None:
        if self.early_fail_window <= 0 or current_profit > self.early_fail_max_profit:
            return None

        open_time = pd.Timestamp(trade.open_date_utc)
        if open_time.tzinfo is None:
            open_time = open_time.tz_localize("UTC")
        else:
            open_time = open_time.tz_convert("UTC")

        dates = pd.to_datetime(candles_until_now["date"], utc=True)
        post_entry = candles_until_now.loc[dates > open_time]
        if post_entry.empty:
            return None
        if len(post_entry) > self.early_fail_window:
            return None

        last_candle = post_entry.iloc[-1]
        atr = float(entry_candle.get("atr_14", 0.0))
        buffer = atr * self.early_fail_atr_buffer
        close = float(last_candle.get("close", current_rate))

        if is_short:
            breakout_line = float(entry_candle.get("pullback_stop_short_line", float("nan")))
            cluster_line = float(entry_candle.get("cluster_zone_low", float("nan")))
            entry_low = float(entry_candle.get("low", float("nan")))
            back_inside_body = pd.notna(breakout_line) and close > breakout_line + buffer
            failed_to_extend = (
                len(post_entry) >= self.early_fail_window
                and pd.notna(entry_low)
                and pd.notna(cluster_line)
                and float(post_entry["low"].min()) >= entry_low - buffer
                and close >= cluster_line - buffer
            )
            if back_inside_body or failed_to_extend:
                return "short_early_false_breakout_exit"
            return None

        breakout_line = float(entry_candle.get("pullback_stop_long_line", float("nan")))
        cluster_line = float(entry_candle.get("cluster_zone_high", float("nan")))
        entry_high = float(entry_candle.get("high", float("nan")))
        back_inside_body = pd.notna(breakout_line) and close < breakout_line - buffer
        failed_to_extend = (
            len(post_entry) >= self.early_fail_window
            and pd.notna(entry_high)
            and pd.notna(cluster_line)
            and float(post_entry["high"].max()) <= entry_high + buffer
            and close <= cluster_line + buffer
        )
        if back_inside_body or failed_to_extend:
            return "long_early_false_breakout_exit"
        return None

    def _structure_target(self, entry_candle: pd.Series, is_short: bool) -> float:
        if self.use_pivot_structure:
            pivot_col = "prev_pivot_low" if is_short else "prev_pivot_high"
            pivot = entry_candle.get(pivot_col, float("nan"))
            if pd.notna(pivot) and pivot > 0:
                return float(pivot)

        swing_col = "prev_swing_low" if is_short else "prev_swing_high"
        swing = entry_candle.get(swing_col, float("nan"))
        if pd.notna(swing) and swing > 0:
            return float(swing)
        return float("nan")

    def _mark_first_pullback_after_breakout(self, dataframe: DataFrame, direction: str) -> tuple[pd.Series, pd.Series]:
        """标记突破后的第一次回踩/反抽实体边界。

        direction = "long"：向上突破后，记录突破 K 线实体下沿。
        后面第一根真正回踩 K 线，只要最低价不跌破该实体下沿，就开多。

        direction = "short"：向下跌破后，记录突破 K 线实体上沿。
        后面第一根真正反抽 K 线，只要最高价不突破该实体上沿，就开空。
        """

        waiting_for_pullback = False
        bars_after_breakout = 0
        active_line = float("nan")
        signals: list[bool] = []
        stop_lines: list[float] = []
        signal_types: list[str] = []

        open_values = dataframe["open"].to_numpy()
        close_values = dataframe["close"].to_numpy()
        low_values = dataframe["low"].to_numpy()
        high_values = dataframe["high"].to_numpy()
        atr_values = dataframe["atr_14"].fillna(0.0).to_numpy()
        cluster_high_values = dataframe["cluster_zone_high"].to_numpy()
        cluster_low_values = dataframe["cluster_zone_low"].to_numpy()
        ma_high_values = dataframe["ma_high"].to_numpy()
        ma_low_values = dataframe["ma_low"].to_numpy()
        long_score_values = dataframe["long_direction_score"].fillna(0).to_numpy()
        short_score_values = dataframe["short_direction_score"].fillna(0).to_numpy()

        if direction == "long":
            breakout = dataframe["cluster_breakout_up"].fillna(False).to_numpy()
            breakout_type = dataframe["cluster_breakout_type_up"].fillna("").to_numpy()
            invalid = dataframe["cluster_stop_long"].fillna(False).to_numpy()
        else:
            breakout = dataframe["cluster_breakout_down"].fillna(False).to_numpy()
            breakout_type = dataframe["cluster_breakout_type_down"].fillna("").to_numpy()
            invalid = dataframe["cluster_stop_short"].fillna(False).to_numpy()

        active_type = ""
        active_cluster_high = float("nan")
        active_cluster_low = float("nan")
        waiting_for_confirmation = False
        bars_after_pullback = 0
        pending_line = float("nan")
        pending_type = ""
        pending_cluster_high = float("nan")
        pending_cluster_low = float("nan")
        pending_pullback_high = float("nan")
        pending_pullback_low = float("nan")
        for i in range(len(dataframe)):
            signal = False
            signal_line = float("nan")
            signal_type = ""

            if breakout[i]:
                waiting_for_pullback = True
                bars_after_breakout = 0
                active_type = str(breakout_type[i])
                active_cluster_high = cluster_high_values[i]
                active_cluster_low = cluster_low_values[i]
                if direction == "long":
                    active_line = min(open_values[i], close_values[i])
                else:
                    active_line = max(open_values[i], close_values[i])
                waiting_for_confirmation = False
                bars_after_pullback = 0
            elif waiting_for_pullback:
                bars_after_breakout += 1

            if waiting_for_confirmation:
                bars_after_pullback += 1
                zone_buffer = max(
                    close_values[i] * self.pullback_confirm_zone_pct_buffer,
                    atr_values[i] * self.pullback_confirm_zone_atr_buffer,
                )
                body_pct = abs(close_values[i] - open_values[i]) / close_values[i] if close_values[i] > 0 else 0.0
                if direction == "long":
                    stop_line = pending_line - atr_values[i] * self.body_stop_atr_buffer
                    invalid_confirmation = low_values[i] < stop_line
                    reclaimed_pullback = close_values[i] > pending_pullback_high
                    resumed_strength = (
                        close_values[i] > open_values[i]
                        and close_values[i] > close_values[i - 1]
                        and close_values[i] > ma_high_values[i]
                    )
                    confirmed = (
                        close_values[i] > open_values[i]
                        and body_pct >= self.pullback_confirm_body_pct_min
                        and
                        close_values[i] > pending_cluster_high + zone_buffer
                        and long_score_values[i] >= self.pullback_confirm_score_threshold
                        and (reclaimed_pullback or resumed_strength)
                    )
                else:
                    stop_line = pending_line + atr_values[i] * self.body_stop_atr_buffer
                    invalid_confirmation = high_values[i] > stop_line
                    reclaimed_pullback = close_values[i] < pending_pullback_low
                    resumed_strength = (
                        close_values[i] < open_values[i]
                        and close_values[i] < close_values[i - 1]
                        and close_values[i] < ma_low_values[i]
                    )
                    confirmed = (
                        close_values[i] < open_values[i]
                        and body_pct >= self.pullback_confirm_body_pct_min
                        and
                        close_values[i] < pending_cluster_low - zone_buffer
                        and short_score_values[i] >= self.pullback_confirm_score_threshold
                        and (reclaimed_pullback or resumed_strength)
                    )

                if confirmed:
                    signal = True
                    signal_line = pending_line
                    signal_type = pending_type
                    waiting_for_confirmation = False
                elif invalid_confirmation or bars_after_pullback > self.pullback_reclaim_window:
                    waiting_for_confirmation = False

            if waiting_for_pullback and bars_after_breakout > 0:
                if direction == "long":
                    is_first_pullback = (
                        close_values[i] < close_values[i - 1]
                        or low_values[i] < low_values[i - 1]
                        or close_values[i] < open_values[i]
                    )
                    body_tolerance = close_values[i] * self.body_line_tolerance_pct
                    cluster_tolerance = atr_values[i] * self.cluster_line_tolerance_atr
                    holds_breakout_line = low_values[i] >= active_line - body_tolerance
                    holds_cluster_line = close_values[i] >= active_cluster_high - cluster_tolerance
                else:
                    is_first_pullback = (
                        close_values[i] > close_values[i - 1]
                        or high_values[i] > high_values[i - 1]
                        or close_values[i] > open_values[i]
                    )
                    body_tolerance = close_values[i] * self.body_line_tolerance_pct
                    cluster_tolerance = atr_values[i] * self.cluster_line_tolerance_atr
                    holds_breakout_line = high_values[i] <= active_line + body_tolerance
                    holds_cluster_line = close_values[i] <= active_cluster_low + cluster_tolerance

                if is_first_pullback:
                    holds_reference = holds_breakout_line
                    if active_type == "weak":
                        holds_reference = holds_breakout_line or holds_cluster_line
                    if holds_reference:
                        waiting_for_confirmation = True
                        bars_after_pullback = 0
                        pending_line = active_line
                        pending_type = active_type
                        pending_cluster_high = active_cluster_high
                        pending_cluster_low = active_cluster_low
                        pending_pullback_high = high_values[i]
                        pending_pullback_low = low_values[i]
                    waiting_for_pullback = False

            if waiting_for_pullback and (bars_after_breakout > self.pullback_window or invalid[i]):
                waiting_for_pullback = False
            if waiting_for_confirmation and invalid[i]:
                waiting_for_confirmation = False

            signals.append(signal)
            stop_lines.append(signal_line)
            signal_types.append(signal_type)

        return (
            pd.Series(signals, index=dataframe.index),
            pd.Series(stop_lines, index=dataframe.index),
            pd.Series(signal_types, index=dataframe.index),
        )

    def _populate_htf_indicators(self, dataframe: DataFrame) -> DataFrame:
        """4h 看大做小过滤：只允许顺着高周期结构做 1h 突破回踩。"""
        dataframe["ma_5"] = self._sma(dataframe["close"], 5)
        dataframe["ma_10"] = self._sma(dataframe["close"], 10)
        dataframe["ma_30"] = self._sma(dataframe["close"], 30)
        dataframe["ema_5"] = self._ema(dataframe["close"], 5)
        dataframe["ema_10"] = self._ema(dataframe["close"], 10)
        dataframe["ema_30"] = self._ema(dataframe["close"], 30)
        dataframe["fast_mid"] = (dataframe["ma_5"] + dataframe["ema_5"]) / 2
        dataframe["mid_mid"] = (dataframe["ma_10"] + dataframe["ema_10"]) / 2
        dataframe["slow_mid"] = (dataframe["ma_30"] + dataframe["ema_30"]) / 2
        dataframe["ma_high"] = dataframe[["ma_5", "ma_10", "ma_30", "ema_5", "ema_10", "ema_30"]].max(axis=1)
        dataframe["ma_low"] = dataframe[["ma_5", "ma_10", "ma_30", "ema_5", "ema_10", "ema_30"]].min(axis=1)
        dataframe["fast_mid_slope"] = dataframe["fast_mid"] / dataframe["fast_mid"].shift(self.direction_slope_lookback) - 1
        dataframe["long_direction_score"] = (
            (dataframe["fast_mid"] > dataframe["mid_mid"]).astype(int)
            + (dataframe["mid_mid"] > dataframe["slow_mid"]).astype(int)
            + (dataframe["fast_mid_slope"] > self.htf_slope_min).astype(int)
            + (dataframe["close"] > dataframe["slow_mid"]).astype(int)
            + (dataframe["close"] > dataframe["ma_high"]).astype(int)
        )
        dataframe["short_direction_score"] = (
            (dataframe["fast_mid"] < dataframe["mid_mid"]).astype(int)
            + (dataframe["mid_mid"] < dataframe["slow_mid"]).astype(int)
            + (dataframe["fast_mid_slope"] < -self.htf_slope_min).astype(int)
            + (dataframe["close"] < dataframe["slow_mid"]).astype(int)
            + (dataframe["close"] < dataframe["ma_low"]).astype(int)
        )
        dataframe["htf_long_ok"] = dataframe["long_direction_score"] >= self.htf_score_min
        dataframe["htf_short_ok"] = dataframe["short_direction_score"] >= self.htf_score_min
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if (self.use_htf_context or self.use_htf_filter) and self.dp:
            informative = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=self.informative_timeframe)
            informative = self._populate_htf_indicators(informative.copy())
            dataframe = merge_informative_pair(
                dataframe,
                informative,
                self.timeframe,
                self.informative_timeframe,
                ffill=True,
            )

        dataframe["is_weekend"] = pd.to_datetime(dataframe["date"], utc=True).dt.dayofweek >= 5
        dataframe["ma_5"] = self._sma(dataframe["close"], 5)
        dataframe["ma_10"] = self._sma(dataframe["close"], 10)
        dataframe["ma_30"] = self._sma(dataframe["close"], 30)
        dataframe["ema_5"] = self._ema(dataframe["close"], 5)
        dataframe["ema_10"] = self._ema(dataframe["close"], 10)
        dataframe["ema_30"] = self._ema(dataframe["close"], 30)
        dataframe["atr_14"] = self._true_range(dataframe).rolling(14, min_periods=14).mean()
        dataframe["prev_swing_high"] = dataframe["high"].shift(1).rolling(
            self.swing_lookback,
            min_periods=20,
        ).max()
        dataframe["prev_swing_low"] = dataframe["low"].shift(1).rolling(
            self.swing_lookback,
            min_periods=20,
        ).min()
        pivot_window = self.pivot_left_bars + self.pivot_right_bars + 1
        pivot_high_center = dataframe["high"].shift(self.pivot_right_bars)
        pivot_low_center = dataframe["low"].shift(self.pivot_right_bars)
        confirmed_pivot_high = pivot_high_center.where(
            pivot_high_center >= dataframe["high"].rolling(pivot_window, min_periods=pivot_window).max()
        )
        confirmed_pivot_low = pivot_low_center.where(
            pivot_low_center <= dataframe["low"].rolling(pivot_window, min_periods=pivot_window).min()
        )
        dataframe["prev_pivot_high"] = confirmed_pivot_high.ffill().shift(1)
        dataframe["prev_pivot_low"] = confirmed_pivot_low.ffill().shift(1)

        ma_cols = ["ma_5", "ma_10", "ma_30", "ema_5", "ema_10", "ema_30"]
        dataframe["ma_high"] = dataframe[ma_cols].max(axis=1)
        dataframe["ma_low"] = dataframe[ma_cols].min(axis=1)
        dataframe["ma_width"] = (dataframe["ma_high"] - dataframe["ma_low"]) / dataframe["close"]
        slope_cols = []
        for column in ma_cols:
            slope_column = f"{column}_flat_slope"
            dataframe[slope_column] = (dataframe[column] / dataframe[column].shift(self.ma_flat_slope_lookback) - 1).abs()
            slope_cols.append(slope_column)
        dataframe["ma_max_flat_slope"] = dataframe[slope_cols].max(axis=1)
        dataframe["ma_slopes_flat"] = dataframe["ma_max_flat_slope"] <= self.ma_flat_slope_threshold

        dataframe["ma_width_quantile"] = dataframe["ma_width"].rolling(
            self.ma_cluster_quantile_window,
            min_periods=self.ma_cluster_quantile_window,
        ).quantile(self.ma_cluster_quantile)
        dataframe["price_near_bundle"] = (
            (dataframe["close"] <= dataframe["ma_high"] + dataframe["atr_14"] * self.cluster_price_atr_tolerance)
            & (dataframe["close"] >= dataframe["ma_low"] - dataframe["atr_14"] * self.cluster_price_atr_tolerance)
        )
        dataframe["ma_width_recent_max"] = dataframe["ma_width"].rolling(
            self.ma_cluster_compression_window,
            min_periods=max(6, self.ma_cluster_compression_window // 2),
        ).max()
        dataframe["ma_width_recently_compressed"] = (
            dataframe["ma_width"] <= dataframe["ma_width_recent_max"] * self.ma_cluster_recent_compression_ratio
        )
        dataframe["fast_mid"] = (dataframe["ma_5"] + dataframe["ema_5"]) / 2
        dataframe["mid_mid"] = (dataframe["ma_10"] + dataframe["ema_10"]) / 2
        dataframe["slow_mid"] = (dataframe["ma_30"] + dataframe["ema_30"]) / 2
        dataframe["fast_mid_slope"] = dataframe["fast_mid"] / dataframe["fast_mid"].shift(self.direction_slope_lookback) - 1
        dataframe["group_high"] = dataframe[["fast_mid", "mid_mid", "slow_mid"]].max(axis=1)
        dataframe["group_low"] = dataframe[["fast_mid", "mid_mid", "slow_mid"]].min(axis=1)
        dataframe["group_spread"] = (dataframe["group_high"] - dataframe["group_low"]) / dataframe["close"]
        dataframe["group_spread_contracting"] = (
            dataframe["group_spread"]
            <= dataframe["group_spread"].shift(self.ma_group_contract_window) * self.ma_group_contract_ratio
        )
        dataframe["price_range"] = (
            dataframe["high"].rolling(self.sideways_lookback, min_periods=self.sideways_lookback).max()
            - dataframe["low"].rolling(self.sideways_lookback, min_periods=self.sideways_lookback).min()
        )
        dataframe["price_sideways"] = (
            (dataframe["price_range"] <= dataframe["atr_14"] * self.sideways_range_atr_max)
            | (dataframe["price_range"] / dataframe["close"] <= self.sideways_range_pct_max)
        )
        dataframe["ma_cluster_candidate"] = (
            (dataframe["ma_width"] <= self.ma_cluster_width_threshold)
            & (
                (dataframe["ma_width"] <= dataframe["ma_width_quantile"])
                | dataframe["ma_width_recently_compressed"]
            )
            & dataframe["ma_slopes_flat"]
            & dataframe["group_spread_contracting"]
            & dataframe["price_sideways"]
            & dataframe["price_near_bundle"]
        )
        dataframe["ma_cluster_confirmed"] = (
            dataframe["ma_cluster_candidate"]
            .rolling(self.cluster_confirm_window, min_periods=self.cluster_confirm_window)
            .sum()
            >= self.cluster_confirm_min_bars
        )

        dataframe["long_direction_score"] = (
            (dataframe["fast_mid"] > dataframe["mid_mid"]).astype(int)
            + (dataframe["mid_mid"] > dataframe["slow_mid"]).astype(int)
            + (dataframe["fast_mid_slope"] > 0).astype(int)
            + (dataframe["close"] > dataframe["slow_mid"]).astype(int)
            + (dataframe["close"] > dataframe["ma_high"]).astype(int)
        )
        dataframe["short_direction_score"] = (
            (dataframe["fast_mid"] < dataframe["mid_mid"]).astype(int)
            + (dataframe["mid_mid"] < dataframe["slow_mid"]).astype(int)
            + (dataframe["fast_mid_slope"] < 0).astype(int)
            + (dataframe["close"] < dataframe["slow_mid"]).astype(int)
            + (dataframe["close"] < dataframe["ma_low"]).astype(int)
        )

        dataframe["bullish_ma_order"] = dataframe["long_direction_score"] >= self.strong_breakout_score_threshold
        dataframe["bearish_ma_order"] = dataframe["short_direction_score"] >= self.strong_breakout_score_threshold

        dataframe = self._mark_cluster_state(dataframe)

        dataframe["fast_band_high"] = dataframe[["ma_5", "ema_5"]].max(axis=1)
        dataframe["fast_band_low"] = dataframe[["ma_5", "ema_5"]].min(axis=1)

        dataframe["pullback_5_no_break_long"] = (
            dataframe["bullish_ma_order"]
            & (dataframe["low"] <= dataframe["fast_band_high"] * (1 + self.pullback_touch_tolerance))
            & (dataframe["close"] >= dataframe["fast_band_low"])
            & (dataframe["close"] > dataframe["open"])
        )
        dataframe["pullback_5_no_break_short"] = (
            dataframe["bearish_ma_order"]
            & (dataframe["high"] >= dataframe["fast_band_low"] * (1 - self.pullback_touch_tolerance))
            & (dataframe["close"] <= dataframe["fast_band_high"])
            & (dataframe["close"] < dataframe["open"])
        )

        dataframe["cluster_stop_long"] = (
            (dataframe["close"] < dataframe["cluster_zone_low"] - dataframe["atr_14"] * self.invalid_break_atr_buffer)
            & (dataframe["close"].shift(1) < dataframe["cluster_zone_low"].shift(1) - dataframe["atr_14"].shift(1) * self.invalid_break_atr_buffer)
        )
        dataframe["cluster_stop_short"] = (
            (dataframe["close"] > dataframe["cluster_zone_high"] + dataframe["atr_14"] * self.invalid_break_atr_buffer)
            & (dataframe["close"].shift(1) > dataframe["cluster_zone_high"].shift(1) + dataframe["atr_14"].shift(1) * self.invalid_break_atr_buffer)
        )
        dataframe["effective_break_20_long"] = (
            (dataframe["close"] < dataframe["fast_band_low"] - dataframe["atr_14"] * self.stop_atr_buffer)
            & (dataframe["close"].shift(1) < dataframe["fast_band_low"].shift(1) - dataframe["atr_14"].shift(1) * self.stop_atr_buffer)
        )
        dataframe["effective_break_20_short"] = (
            (dataframe["close"] > dataframe["fast_band_high"] + dataframe["atr_14"] * self.stop_atr_buffer)
            & (dataframe["close"].shift(1) > dataframe["fast_band_high"].shift(1) + dataframe["atr_14"].shift(1) * self.stop_atr_buffer)
        )

        (
            dataframe["first_pullback_long"],
            dataframe["pullback_stop_long_line"],
            dataframe["pullback_type_long"],
        ) = self._mark_first_pullback_after_breakout(dataframe, "long")
        (
            dataframe["first_pullback_short"],
            dataframe["pullback_stop_short_line"],
            dataframe["pullback_type_short"],
        ) = self._mark_first_pullback_after_breakout(dataframe, "short")

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if self.use_htf_filter and "htf_long_ok_4h" in dataframe:
            long_htf_ok = dataframe["htf_long_ok_4h"].fillna(False)
            short_htf_ok = dataframe["htf_short_ok_4h"].fillna(False)
        else:
            long_htf_ok = True
            short_htf_ok = True

        if self.weekend_entry_mode == 2:
            weekend_entry_ok = ~dataframe["is_weekend"].fillna(False)
        else:
            weekend_entry_ok = True

        dataframe.loc[
            (dataframe["volume"] > 0)
            & dataframe["first_pullback_long"]
            & (dataframe["pullback_type_long"] == "strong")
            & long_htf_ok
            & weekend_entry_ok,
            ["enter_long", "enter_tag"],
        ] = (int(self.trade_strong_breakouts), "long_strong_breakout_pullback")

        dataframe.loc[
            (dataframe["volume"] > 0)
            & dataframe["first_pullback_long"]
            & (dataframe["pullback_type_long"] == "weak")
            & long_htf_ok
            & weekend_entry_ok,
            ["enter_long", "enter_tag"],
        ] = (int(self.trade_weak_breakouts), "long_weak_breakout_pullback")

        dataframe.loc[
            (dataframe["volume"] > 0)
            & dataframe["first_pullback_short"]
            & (dataframe["pullback_type_short"] == "strong")
            & short_htf_ok
            & weekend_entry_ok,
            ["enter_short", "enter_tag"],
        ] = (int(self.trade_strong_breakouts), "short_strong_breakout_pullback")

        dataframe.loc[
            (dataframe["volume"] > 0)
            & dataframe["first_pullback_short"]
            & (dataframe["pullback_type_short"] == "weak")
            & short_htf_ok
            & weekend_entry_ok,
            ["enter_short", "enter_tag"],
        ] = (int(self.trade_weak_breakouts), "short_weak_breakout_pullback")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | None:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if dataframe.empty:
            return None

        candles_until_now = self._candles_until(dataframe, current_time)
        if candles_until_now.empty:
            return None

        last_candle = candles_until_now.iloc[-1]
        entry_tag = getattr(trade, "enter_tag", None) or getattr(trade, "entry_tag", None) or ""
        is_short = bool(getattr(trade, "is_short", False))
        trade_key = self._trade_key(pair, trade)
        if not hasattr(self, "_trade_peak_profit"):
            self._trade_peak_profit = {}
        peak_profit = max(self._trade_peak_profit.get(trade_key, current_profit), current_profit)
        self._trade_peak_profit[trade_key] = peak_profit

        if "cluster_breakout" in entry_tag:
            if is_short and bool(last_candle.get("cluster_stop_short", False)):
                return "short_cluster_zone_invalid"
            if not is_short and bool(last_candle.get("cluster_stop_long", False)):
                return "long_cluster_zone_invalid"

        if "pullback" in entry_tag:
            entry_candle = self._entry_candle(candles_until_now, trade)
            if entry_candle is not None:
                early_exit = self._early_false_breakout_exit(
                    candles_until_now,
                    entry_candle,
                    trade,
                    current_rate,
                    current_profit,
                    is_short,
                )
                if early_exit is not None:
                    return early_exit

                entry_stop_rate = self._planned_stop_rate(entry_candle, entry_tag, is_short)
                if entry_stop_rate is not None:
                    if is_short and current_rate > entry_stop_rate:
                        return "short_breakout_body_line_invalid"
                    if not is_short and current_rate < entry_stop_rate:
                        return "long_breakout_body_line_invalid"

        entry_candle = self._entry_candle(candles_until_now, trade)
        if entry_candle is None:
            return None

        entry_rate = float(getattr(trade, "open_rate", 0.0))
        stop_rate = self._planned_stop_rate(entry_candle, entry_tag, is_short)
        if entry_rate <= 0 or stop_rate is None:
            return None

        target_rate = self._take_profit_rate(entry_candle, entry_rate, stop_rate, is_short)
        if target_rate is None:
            return None

        if is_short and current_rate <= target_rate:
            return "short_rr_structure_take_profit"
        if not is_short and current_rate >= target_rate:
            return "long_rr_structure_take_profit"

        trailing_start = self._trailing_start(entry_candle, is_short)
        if self._trailing_enabled(entry_candle, is_short) and peak_profit >= trailing_start:
            giveback_exit_profit = peak_profit * self._trailing_retrace_ratio(entry_candle, is_short)
            if current_profit <= giveback_exit_profit:
                return "large_profit_50pct_giveback"

        return None
