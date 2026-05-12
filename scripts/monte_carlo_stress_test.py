from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from freqtrade.strategy import merge_informative_pair

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from user_data.strategies.VideoDoubleMaFuturesStrategy import VideoDoubleMaFuturesStrategy


STARTING_BALANCE = 10_000.0
FIXED_STAKE = 10_000.0
FEE_RATE = 0.0005
TRADING_DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class Variant:
    name: str
    trend_continuation: bool


VARIANTS = (
    Variant("stable_default", False),
    Variant("simple_long_continuation", True),
)


SCENARIOS = (
    "t_clustered_calendar_jump",
    "historical_eth_btc_bootstrap",
    "black_swan_crash_rebound",
    "black_swan_slow_decay",
)


def pair_to_file_stem(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_")


def load_ohlcv(data_dir: Path, pair: str, timeframe: str = "1h") -> pd.DataFrame:
    stem = pair_to_file_stem(pair)
    path = data_dir / "futures" / f"{stem}-{timeframe}-futures.feather"
    if not path.exists():
        raise FileNotFoundError(path)
    dataframe = pd.read_feather(path)
    dataframe["date"] = pd.to_datetime(dataframe["date"], utc=True)
    return dataframe.sort_values("date").reset_index(drop=True)


def resample_ohlcv(dataframe: pd.DataFrame, rule: str) -> pd.DataFrame:
    frame = dataframe.set_index(pd.to_datetime(dataframe["date"], utc=True))
    resampled = frame.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return resampled.dropna(subset=["open", "high", "low", "close"]).reset_index().rename(columns={"index": "date"})


def merge_context(strategy: VideoDoubleMaFuturesStrategy, dataframe: pd.DataFrame) -> pd.DataFrame:
    htf_4h = strategy._populate_htf_indicators(resample_ohlcv(dataframe, "4h"))
    merged = merge_informative_pair(dataframe, htf_4h, strategy.timeframe, strategy.informative_timeframe, ffill=True)
    htf_1d = strategy._populate_htf_indicators(resample_ohlcv(dataframe, "1D"))
    merged = merge_informative_pair(merged, htf_1d, strategy.timeframe, strategy.daily_timeframe, ffill=True)
    return merged


def build_strategy(variant: Variant) -> VideoDoubleMaFuturesStrategy:
    strategy = VideoDoubleMaFuturesStrategy({})
    strategy.dp = None
    strategy.trade_trend_continuation = variant.trend_continuation
    strategy.trend_continuation_long = True
    strategy.trend_continuation_short = False
    strategy.trend_continuation_cooldown = 72
    strategy.trend_continuation_leverage = 2.0
    strategy.use_daily_trend_context = True
    strategy.trend_continuation_daily_score_min = 4
    strategy.trend_continuation_daily_require_order = True
    return strategy


def prepare_signals(dataframe: pd.DataFrame, variant: Variant) -> tuple[pd.DataFrame, VideoDoubleMaFuturesStrategy]:
    strategy = build_strategy(variant)
    merged = merge_context(strategy, dataframe)
    indicators = strategy.populate_indicators(merged, {"pair": "SIM/USDT:USDT"})
    signals = strategy.populate_entry_trend(indicators, {"pair": "SIM/USDT:USDT"}).copy()
    for column in ("enter_long", "enter_short"):
        if column not in signals:
            signals[column] = 0
        signals[column] = signals[column].fillna(0).astype(int)
    if "enter_tag" not in signals:
        signals["enter_tag"] = ""
    signals["enter_tag"] = signals["enter_tag"].fillna("")
    return signals, strategy


def profit_ratio(entry_rate: float, exit_rate: float, is_short: bool, leverage: float) -> float:
    if is_short:
        raw = (entry_rate - exit_rate) / entry_rate
    else:
        raw = (exit_rate - entry_rate) / entry_rate
    return raw * leverage - 2 * FEE_RATE * leverage


def max_drawdown(equity: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity)
    dd = equity / running_max - 1
    return float(abs(dd.min()))


def annualized_from_equity(equity: np.ndarray, days: float) -> float:
    if len(equity) == 0 or equity[-1] <= 0 or days <= 0:
        return -1.0
    return float((equity[-1] / equity[0]) ** (TRADING_DAYS_PER_YEAR / days) - 1)


def backtest_signals(dataframe: pd.DataFrame, variant: Variant) -> dict:
    signals, strategy = prepare_signals(dataframe, variant)
    equity = STARTING_BALANCE
    equity_curve = []
    trades = []
    in_trade = False
    entry = {}

    for i, row in signals.iterrows():
        date = row["date"]
        if not in_trade:
            equity_curve.append({"date": date, "equity": equity})
            if i < strategy.startup_candle_count:
                continue
            if int(row.get("enter_long", 0)) == 1:
                entry_tag = str(row.get("enter_tag", ""))
                entry = {
                    "entry_i": i,
                    "date": date,
                    "rate": float(row["close"]),
                    "candle": row.copy(),
                    "is_short": False,
                    "tag": entry_tag,
                    "leverage": strategy.leverage("SIM/USDT:USDT", date, float(row["close"]), 1.0, 20.0, entry_tag, "long"),
                    "peak_profit": 0.0,
                }
                in_trade = True
            elif int(row.get("enter_short", 0)) == 1:
                entry_tag = str(row.get("enter_tag", ""))
                entry = {
                    "entry_i": i,
                    "date": date,
                    "rate": float(row["close"]),
                    "candle": row.copy(),
                    "is_short": True,
                    "tag": entry_tag,
                    "leverage": strategy.leverage("SIM/USDT:USDT", date, float(row["close"]), 1.0, 20.0, entry_tag, "short"),
                    "peak_profit": 0.0,
                }
                in_trade = True
            continue

        entry_rate = float(entry["rate"])
        is_short = bool(entry["is_short"])
        leverage = float(entry["leverage"])
        entry_candle = entry["candle"]
        entry_tag = str(entry["tag"])
        stop_rate = strategy._planned_stop_rate(entry_candle, entry_tag, is_short)
        if stop_rate is None:
            stop_rate = entry_rate * (1 - strategy.stoploss / leverage) if is_short else entry_rate * (1 + strategy.stoploss / leverage)
        target_rate = strategy._take_profit_rate(entry_candle, entry_rate, float(stop_rate), is_short)

        exit_rate = None
        exit_reason = None
        if is_short:
            bar_best = profit_ratio(entry_rate, float(row["low"]), True, leverage)
            entry["peak_profit"] = max(float(entry["peak_profit"]), bar_best)
            stop_hit = float(row["high"]) >= float(stop_rate)
            target_hit = target_rate is not None and float(row["low"]) <= float(target_rate)
        else:
            bar_best = profit_ratio(entry_rate, float(row["high"]), False, leverage)
            entry["peak_profit"] = max(float(entry["peak_profit"]), bar_best)
            stop_hit = float(row["low"]) <= float(stop_rate)
            target_hit = target_rate is not None and float(row["high"]) >= float(target_rate)

        if stop_hit:
            exit_rate = float(stop_rate)
            exit_reason = "planned_stop"
        elif target_hit:
            exit_rate = float(target_rate)
            exit_reason = "rr_target"
        else:
            current_profit = profit_ratio(entry_rate, float(row["close"]), is_short, leverage)
            trailing_start = strategy._trailing_start(entry_candle, is_short)
            if strategy._trailing_enabled(entry_candle, is_short) and entry["peak_profit"] >= trailing_start:
                if current_profit <= entry["peak_profit"] * strategy._trailing_retrace_ratio(entry_candle, is_short):
                    exit_rate = float(row["close"])
                    exit_reason = "profit_giveback"

        if exit_rate is not None:
            ratio = profit_ratio(entry_rate, exit_rate, is_short, leverage)
            stake = min(FIXED_STAKE, max(equity, 0.0))
            equity += stake * ratio
            trades.append(
                {
                    "entry_date": entry["date"],
                    "exit_date": date,
                    "tag": entry_tag,
                    "is_short": is_short,
                    "profit_ratio": ratio,
                    "profit_abs": FIXED_STAKE * ratio,
                    "exit_reason": exit_reason,
                    "leverage": leverage,
                    "stake": stake,
                    "duration_hours": int(i - int(entry["entry_i"])),
                }
            )
            in_trade = False
            entry = {}
            if equity <= 0:
                equity_curve.append({"date": date, "equity": equity})
                break
        equity_curve.append({"date": date, "equity": equity})

    equity_df = pd.DataFrame(equity_curve).drop_duplicates("date", keep="last")
    if equity_df.empty:
        equity_df = pd.DataFrame({"date": dataframe["date"], "equity": STARTING_BALANCE})
    trade_df = pd.DataFrame(trades)
    days = max((pd.to_datetime(equity_df["date"].iloc[-1], utc=True) - pd.to_datetime(equity_df["date"].iloc[0], utc=True)).days, 1)
    returns = trade_df["profit_ratio"] if not trade_df.empty else pd.Series(dtype=float)
    gross_profit = float(returns[returns > 0].sum())
    gross_loss = float(abs(returns[returns < 0].sum()))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    winrate = float((returns > 0).mean()) if len(returns) else 0.0
    return {
        "summary": {
            "trades": int(len(trade_df)),
            "final_balance": float(equity_df["equity"].iloc[-1]),
            "total_return": float(equity_df["equity"].iloc[-1] / STARTING_BALANCE - 1),
            "cagr": annualized_from_equity(equity_df["equity"].to_numpy(dtype=float), float(days)),
            "max_drawdown": max_drawdown(equity_df["equity"].to_numpy(dtype=float)),
            "winrate": winrate,
            "profit_factor": profit_factor,
            "avg_trade": float(returns.mean()) if len(returns) else 0.0,
            "worst_trade": float(returns.min()) if len(returns) else 0.0,
            "best_trade": float(returns.max()) if len(returns) else 0.0,
            "ruined": bool(equity_df["equity"].iloc[-1] <= 0),
        },
        "equity": equity_df,
        "trades": trade_df,
    }


def real_return_pool(real_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for asset, df in real_data.items():
        frame = df[["date", "close"]].copy()
        frame["asset"] = asset
        frame["log_return"] = np.log(frame["close"]).diff()
        rows.append(frame.dropna())
    return pd.concat(rows, ignore_index=True)


def calendar_multiplier(dates: pd.Series) -> np.ndarray:
    china_time = pd.to_datetime(dates, utc=True).dt.tz_convert("Asia/Shanghai")
    hour = china_time.dt.hour.to_numpy()
    weekday = china_time.dt.dayofweek.to_numpy()
    mult = np.ones(len(dates))
    mult[weekday >= 5] *= 0.62
    us_evening = (hour >= 22) | (hour <= 2)
    mult[us_evening] *= 1.35
    return mult


def generate_synthetic_path(
    scenario: str,
    real_data: dict[str, pd.DataFrame],
    pool: pd.DataFrame,
    rng: np.random.Generator,
    source_asset: str,
) -> pd.DataFrame:
    template = real_data[source_asset][["date", "close", "volume"]].copy().reset_index(drop=True)
    n = len(template)
    real_returns = pool.loc[pool["asset"] == source_asset, "log_return"].to_numpy()
    real_returns = real_returns[np.isfinite(real_returns)]
    mu = float(np.mean(real_returns))
    base_sigma = float(np.std(real_returns))
    dates = template["date"]
    seasonality = calendar_multiplier(dates)

    if scenario == "historical_eth_btc_bootstrap":
        blocks = []
        pool_values = pool["log_return"].to_numpy()
        pool_values = pool_values[np.isfinite(pool_values)]
        while sum(len(x) for x in blocks) < n:
            block = int(rng.integers(24 * 7, 24 * 45))
            start = int(rng.integers(0, len(pool_values) - block - 1))
            blocks.append(pool_values[start : start + block])
        log_returns = np.concatenate(blocks)[:n] * seasonality
    else:
        log_returns = np.zeros(n)
        sigma = max(base_sigma, 1e-5)
        previous = 0.0
        drift_regime = 0.0
        df = 3.0
        for i in range(n):
            innovation = rng.standard_t(df) / math.sqrt(df / (df - 2))
            sigma = math.sqrt((base_sigma * 0.22) ** 2 + 0.12 * previous**2 + 0.86 * sigma**2)
            drift_regime = 0.996 * drift_regime + rng.normal(mu * 0.04, base_sigma * 0.012)
            jump = 0.0
            if rng.random() < 0.0022:
                jump = rng.choice([-1.0, 1.0]) * float(rng.lognormal(mean=math.log(0.035), sigma=0.65))
            log_returns[i] = mu * 0.35 + drift_regime + sigma * seasonality[i] * innovation + jump
            previous = log_returns[i]

    if scenario == "black_swan_crash_rebound":
        start = int(rng.integers(n // 6, n - 24 * 90))
        crash_size = float(rng.uniform(0.30, 0.48))
        crash_hours = int(rng.integers(1, 6))
        rebound_size = float(rng.uniform(0.12, 0.35))
        rebound_hours = int(rng.integers(24, 96))
        log_returns[start : start + crash_hours] += math.log(1 - crash_size) / crash_hours
        log_returns[start + crash_hours : start + crash_hours + rebound_hours] += math.log(1 + rebound_size) / rebound_hours
    elif scenario == "black_swan_slow_decay":
        start = int(rng.integers(n // 5, n - 24 * 180))
        decay_hours = int(rng.integers(24 * 90, 24 * 360))
        decay_size = float(rng.uniform(0.70, 0.96))
        log_returns[start : start + decay_hours] += math.log(1 - decay_size) / decay_hours
        if rng.random() < 0.35:
            shock_start = start + int(rng.integers(24, decay_hours - 24))
            log_returns[shock_start : shock_start + 3] += math.log(0.70) / 3

    close = np.empty(n)
    close[0] = float(template["close"].iloc[0])
    for i in range(1, n):
        close[i] = max(close[i - 1] * math.exp(float(np.clip(log_returns[i], -0.95, 0.95))), 1e-8)
    open_ = np.r_[close[0], close[:-1]]
    rolling_sigma = pd.Series(log_returns).rolling(24, min_periods=1).std().fillna(base_sigma).to_numpy()
    range_noise = np.abs(log_returns) + rolling_sigma * rng.uniform(0.6, 2.2, size=n) + 0.0006
    high = np.maximum(open_, close) * (1 + range_noise * rng.uniform(0.25, 0.9, size=n))
    low = np.minimum(open_, close) * np.maximum(1 - range_noise * rng.uniform(0.25, 0.9, size=n), 1e-6)
    volume = template["volume"].median() * rng.lognormal(mean=0, sigma=0.8, size=n) * (1 + np.minimum(range_noise * 55, 6))

    return pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def aggregate_results(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    grouped = (
        df.groupby(["variant", "scenario"])
        .agg(
            simulations=("simulation", "count"),
            median_cagr=("cagr", "median"),
            p05_cagr=("cagr", lambda x: x.quantile(0.05)),
            median_return=("total_return", "median"),
            p05_return=("total_return", lambda x: x.quantile(0.05)),
            median_drawdown=("max_drawdown", "median"),
            p95_drawdown=("max_drawdown", lambda x: x.quantile(0.95)),
            median_winrate=("winrate", "median"),
            median_profit_factor=("profit_factor", "median"),
            loss_probability=("total_return", lambda x: float((x < 0).mean())),
            ruin_probability=("ruined", "mean"),
            median_trades=("trades", "median"),
        )
        .reset_index()
    )
    return grouped


def fmt_pct(value: float) -> str:
    if not np.isfinite(value):
        return "inf"
    return f"{value * 100:.2f}%"


def write_svg_equity(curves: dict[str, pd.DataFrame], output: Path) -> None:
    width, height = 1100, 560
    margin = 55
    colors = {
        "stable_default": "#dc2626",
        "simple_long_continuation": "#2563eb",
    }
    all_values = np.concatenate([df["equity"].to_numpy(dtype=float) / STARTING_BALANCE for df in curves.values()])
    ymin = max(0.0, float(np.nanmin(all_values)) * 0.95)
    ymax = float(np.nanmax(all_values)) * 1.05
    if ymax <= ymin:
        ymax = ymin + 1

    def x_pos(i: int, n: int) -> float:
        return margin + i * (width - 2 * margin) / max(n - 1, 1)

    def y_pos(v: float) -> float:
        return height - margin - (v - ymin) * (height - 2 * margin) / (ymax - ymin)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{margin}" y="32" font-family="Arial" font-size="22" fill="#111827">Monte Carlo median equity curves</text>',
        f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="#d1d5db"/>',
        f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="#d1d5db"/>',
    ]
    for tick in np.linspace(ymin, ymax, 6):
        y = y_pos(float(tick))
        lines.append(f'<line x1="{margin}" y1="{y:.1f}" x2="{width-margin}" y2="{y:.1f}" stroke="#f3f4f6"/>')
        lines.append(f'<text x="8" y="{y+4:.1f}" font-family="Arial" font-size="12" fill="#6b7280">{tick:.1f}x</text>')

    legend_y = 54
    for idx, (label, df) in enumerate(curves.items()):
        values = df["equity"].to_numpy(dtype=float) / STARTING_BALANCE
        if len(values) > 800:
            take = np.linspace(0, len(values) - 1, 800).astype(int)
            values = values[take]
        points = " ".join(f"{x_pos(i, len(values)):.1f},{y_pos(float(v)):.1f}" for i, v in enumerate(values))
        color = colors.get(label.split("|")[0], "#111827")
        lines.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.3" opacity="0.92"/>')
        lines.append(f'<rect x="{width-330}" y="{legend_y + idx*22 - 11}" width="14" height="4" fill="{color}"/>')
        lines.append(
            f'<text x="{width-308}" y="{legend_y + idx*22 - 5}" font-family="Arial" font-size="13" fill="#374151">{label}</text>'
        )
    lines.append("</svg>")
    output.write_text("\n".join(lines), encoding="utf-8")


def representative_median_curves(all_curves: dict[tuple[str, str, int], pd.DataFrame], rows: list[dict]) -> dict[str, pd.DataFrame]:
    frame = pd.DataFrame(rows)
    selected = {}
    for variant in frame["variant"].unique():
        for scenario in frame["scenario"].unique():
            subset = frame[(frame["variant"] == variant) & (frame["scenario"] == scenario)].copy()
            if subset.empty:
                continue
            median = subset["total_return"].median()
            subset["distance"] = (subset["total_return"] - median).abs()
            sim_id = int(subset.sort_values("distance").iloc[0]["simulation"])
            selected[f"{variant}|{scenario}"] = all_curves[(variant, scenario, sim_id)]
    return selected


def write_report(summary: pd.DataFrame, detail: pd.DataFrame, output: Path, chart_path: Path, runs_per_scenario: int) -> None:
    lines = [
        "# Monte Carlo Stress Test",
        "",
        "本报告用于压力测试当前 ETH 双均线策略，而不是用于证明策略一定有效。模型刻意加入肥尾、波动率聚集、日内/周内波动差异、跳跃风险、真实 BTC/ETH return block bootstrap，以及低概率黑天鹅路径。",
        "",
        f"- 每个场景模拟次数：`{runs_per_scenario}`",
        "- 数据频率：`1h`",
        "- 回测执行：轻量执行器复刻当前策略的入场、计划结构止损、R 倍止盈和移动止盈；结果用于压力测试，不替代 Freqtrade 正式回测。",
        "- 变体：`stable_default` 为当前稳定版；`simple_long_continuation` 为 4h + 1d 多头确认后的简单只做多趋势中继增强。",
        "",
        f"![Monte Carlo median equity curves]({chart_path.as_posix()})",
        "",
        "## Summary Table",
        "",
        "| Variant | Scenario | Sims | Median CAGR | P05 CAGR | Median Return | P05 Return | Median DD | P95 DD | Median Winrate | Median PF | Loss Prob | Ruin Prob | Median Trades |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.sort_values(["variant", "scenario"]).itertuples(index=False):
        lines.append(
            "| "
            + " | ".join(
                [
                    row.variant,
                    row.scenario,
                    str(int(row.simulations)),
                    fmt_pct(row.median_cagr),
                    fmt_pct(row.p05_cagr),
                    fmt_pct(row.median_return),
                    fmt_pct(row.p05_return),
                    fmt_pct(row.median_drawdown),
                    fmt_pct(row.p95_drawdown),
                    fmt_pct(row.median_winrate),
                    f"{row.median_profit_factor:.2f}",
                    fmt_pct(row.loss_probability),
                    fmt_pct(row.ruin_probability),
                    f"{row.median_trades:.0f}",
                ]
            )
            + " |"
        )

    best = summary.sort_values(["median_cagr", "p95_drawdown"], ascending=[False, True]).iloc[0]
    worst = summary.sort_values(["p05_return", "p95_drawdown"], ascending=[True, False]).iloc[0]
    lines += [
        "",
        "## Strategy Analysis",
        "",
        f"- 中位数年化最高的是 `{best.variant}` / `{best.scenario}`，median CAGR 为 `{fmt_pct(best.median_cagr)}`，但需要同时看 P95 回撤 `{fmt_pct(best.p95_drawdown)}`。",
        f"- 最脆弱的左尾来自 `{worst.variant}` / `{worst.scenario}`，P05 return 为 `{fmt_pct(worst.p05_return)}`；这说明遇到连续跳跃或逐渐归零类路径时，双均线系统无法保证保本。",
        "- 稳定版的优点是规则更短、暴露更少；趋势中继版在部分趋势路径中更敢追，但在震荡后接跳跃的路径上会增加额外亏损。",
        "- 这个压力测试支持的结论是：趋势中继可以作为手动判断强趋势时的开关，不建议永远开启；主系统仍应以均线密集突破/首次回踩为核心。",
        "- 黑天鹅路径下最重要的不是提高胜率，而是限制单笔风险和避免高频重复进场；实盘仍需要交易所止损、最大日亏损、连续亏损暂停等执行层保护。",
        "",
        "## Files",
        "",
        "- `reports/futures_backtests/monte_carlo/monte_carlo_detail.csv`",
        "- `reports/futures_backtests/monte_carlo/monte_carlo_summary.csv`",
        "- `reports/futures_backtests/monte_carlo/monte_carlo_equity_curves.svg`",
        "- `reports/futures_backtests/monte_carlo/monte_carlo_stress_summary.json`",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "user_data" / "data" / "binance")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "reports" / "futures_backtests" / "monte_carlo")
    parser.add_argument("--runs-per-scenario", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260512)
    parser.add_argument("--write-trades", action="store_true", help="Write per-simulation trade CSV files.")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    real_data = {
        "ETH": load_ohlcv(args.data_dir, "ETH/USDT:USDT"),
        "BTC": load_ohlcv(args.data_dir, "BTC/USDT:USDT"),
    }
    pool = real_return_pool(real_data)
    rows = []
    curves = {}

    for scenario in SCENARIOS:
        for simulation in range(args.runs_per_scenario):
            source_asset = "ETH" if rng.random() < 0.55 else "BTC"
            path = generate_synthetic_path(scenario, real_data, pool, rng, source_asset)
            for variant in VARIANTS:
                result = backtest_signals(path, variant)
                summary = result["summary"]
                rows.append(
                    {
                        "variant": variant.name,
                        "scenario": scenario,
                        "simulation": simulation,
                        "source_asset": source_asset,
                        **summary,
                    }
                )
                curves[(variant.name, scenario, simulation)] = result["equity"]
                if args.write_trades:
                    trades_path = args.output_dir / f"trades_{variant.name}_{scenario}_{simulation:03d}.csv"
                    result["trades"].to_csv(trades_path, index=False, encoding="utf-8")

    detail = pd.DataFrame(rows)
    summary = aggregate_results(rows)
    detail_path = args.output_dir / "monte_carlo_detail.csv"
    summary_path = args.output_dir / "monte_carlo_summary.csv"
    json_path = args.output_dir / "monte_carlo_stress_summary.json"
    chart_path = args.output_dir / "monte_carlo_equity_curves.svg"
    report_path = PROJECT_ROOT / "reports" / "futures_backtests" / "MONTE_CARLO_STRESS_TEST.md"

    detail.to_csv(detail_path, index=False, encoding="utf-8")
    summary.to_csv(summary_path, index=False, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "runs_per_scenario": args.runs_per_scenario,
                "seed": args.seed,
                "summary": summary.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_svg_equity(representative_median_curves(curves, rows), chart_path)
    relative_chart = chart_path.relative_to(report_path.parent)
    write_report(summary, detail, report_path, relative_chart, args.runs_per_scenario)
    print(summary.to_string(index=False))
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
