from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from user_data.strategies.VideoDoubleMaFuturesStrategy import VideoDoubleMaFuturesStrategy


MA_COLORS = {
    "ma_5": "#0891b2",
    "ema_5": "#14b8a6",
    "ma_10": "#facc15",
    "ema_10": "#f59e0b",
    "ma_30": "#7c3aed",
    "ema_30": "#a855f7",
}

CLUSTER_RECTANGLE_STYLE = {
    "line_color": "rgba(15, 23, 42, 0.45)",
    "fillcolor": "rgba(250, 204, 21, 0.16)",
    "line_width": 1,
}


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def pair_to_stem(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_")


def load_backtest(backtest_zip: Path, strategy: str) -> dict:
    with zipfile.ZipFile(backtest_zip) as archive:
        result_name = next(name for name in archive.namelist() if name.endswith(".json") and "_config" not in name)
        data = json.loads(archive.read(result_name))
    return data["strategy"][strategy]


def find_data_file(data_dir: Path, pair: str, timeframe: str) -> Path:
    stem = pair_to_stem(pair)
    candidates = sorted(data_dir.glob(f"{stem}-{timeframe}*.feather"))
    if not candidates and pair.endswith(":USDT"):
        spot_stem = pair_to_stem(pair.replace(":USDT", ""))
        candidates = sorted(data_dir.glob(f"{spot_stem}-{timeframe}*.feather"))
    if not candidates:
        raise FileNotFoundError(f"No feather data found for {pair} {timeframe} in {data_dir}")
    futures_files = [path for path in candidates if path.name.endswith("-futures.feather")]
    return futures_files[0] if futures_files else candidates[0]


def add_indicators(dataframe: pd.DataFrame, pair: str) -> pd.DataFrame:
    strategy = VideoDoubleMaFuturesStrategy({})
    return strategy.populate_indicators(dataframe.copy(), {"pair": pair})


def iter_cluster_rectangles(dataframe: pd.DataFrame):
    """Yield contiguous confirmed MA-cluster zones for Plotly rectangles.

    Adjust the rectangle behavior here if you want wider/narrower visual boxes:
    - `ma_cluster_confirmed` decides which candles belong to a cluster.
    - `ma_low` / `ma_high` define the vertical box around the six-line bundle.
    - The `0.003` padding gives the rectangle a little breathing room.
    """

    if "ma_cluster_confirmed" not in dataframe.columns:
        return

    cluster = dataframe["ma_cluster_confirmed"].fillna(False).astype(bool).to_numpy()
    if len(cluster) == 0:
        return

    start_idx = None
    for idx, is_cluster in enumerate(cluster):
        if is_cluster and start_idx is None:
            start_idx = idx
        if start_idx is not None and (not is_cluster or idx == len(cluster) - 1):
            end_idx = idx if is_cluster and idx == len(cluster) - 1 else idx - 1
            zone = dataframe.iloc[start_idx : end_idx + 1]
            if not zone.empty:
                y0 = float(zone["ma_low"].min())
                y1 = float(zone["ma_high"].max())
                padding = max((y1 - y0) * 0.15, float(zone["close"].median()) * 0.003)
                yield {
                    "x0": zone["date"].iloc[0],
                    "x1": zone["date"].iloc[-1],
                    "y0": y0 - padding,
                    "y1": y1 + padding,
                    "text": (
                        f"MA cluster<br>"
                        f"{zone['date'].iloc[0]} -> {zone['date'].iloc[-1]}<br>"
                        f"min width: {zone['ma_width'].min():.2%}<br>"
                        f"max width: {zone['ma_width'].max():.2%}"
                    ),
                }
            start_idx = None


def add_cluster_rectangles(fig: go.Figure, dataframe: pd.DataFrame) -> None:
    for rect in iter_cluster_rectangles(dataframe):
        fig.add_shape(
            type="rect",
            xref="x",
            yref="y",
            x0=rect["x0"],
            x1=rect["x1"],
            y0=rect["y0"],
            y1=rect["y1"],
            layer="below",
            line={"color": CLUSTER_RECTANGLE_STYLE["line_color"], "width": CLUSTER_RECTANGLE_STYLE["line_width"]},
            fillcolor=CLUSTER_RECTANGLE_STYLE["fillcolor"],
        )
        fig.add_annotation(
            x=rect["x0"],
            y=rect["y1"],
            xref="x",
            yref="y",
            text="cluster",
            showarrow=False,
            font={"size": 10, "color": "#334155"},
            bgcolor="rgba(255, 255, 255, 0.65)",
            bordercolor="rgba(15, 23, 42, 0.2)",
            borderwidth=1,
        )


def add_trade_markers(fig: go.Figure, trades: pd.DataFrame, is_short: bool, is_entry: bool) -> None:
    if trades.empty:
        return

    date_col = "open_date" if is_entry else "close_date"
    rate_col = "open_rate" if is_entry else "close_rate"

    if is_short and is_entry:
        name, color, symbol = "Short entry", "#dc2626", "triangle-down"
    elif is_short and not is_entry:
        name, color, symbol = "Short exit", "#991b1b", "x"
    elif not is_short and is_entry:
        name, color, symbol = "Long entry", "#16a34a", "triangle-up"
    else:
        name, color, symbol = "Long exit", "#166534", "x"

    hover = []
    for trade in trades.to_dict("records"):
        hover.append(
            f"{trade['pair']}<br>"
            f"{trade.get('enter_tag', '')}<br>"
            f"exit: {trade.get('exit_reason', '')}<br>"
            f"account profit: {trade.get('profit_ratio', 0):.2%}<br>"
            f"100U margin ROI approx: {trade.get('profit_ratio', 0) * 100:.2%}"
        )

    fig.add_trace(
        go.Scatter(
            x=trades[date_col],
            y=trades[rate_col],
            mode="markers",
            name=name,
            marker={"color": color, "symbol": symbol, "size": 10, "line": {"width": 1, "color": "#111827"}},
            text=hover,
            hovertemplate="%{text}<extra></extra>",
        )
    )


def parse_utc_date(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return pd.Timestamp(value, tz="UTC")


def plot_pair(
    data_dir: Path,
    output_dir: Path,
    backtest: dict,
    strategy: str,
    pair: str,
    timeframe: str,
    date_from: pd.Timestamp | None = None,
    date_to: pd.Timestamp | None = None,
    show_clusters: bool = True,
) -> Path:
    data_file = find_data_file(data_dir, pair, timeframe)
    dataframe = pd.read_feather(data_file)
    dataframe["date"] = pd.to_datetime(dataframe["date"], utc=True)
    dataframe = add_indicators(dataframe, pair)

    if date_from is not None:
        dataframe = dataframe[dataframe["date"] >= date_from].copy()
    if date_to is not None:
        dataframe = dataframe[dataframe["date"] <= date_to].copy()

    trades = pd.DataFrame(backtest.get("trades", []))
    if not trades.empty:
        trades = trades[trades["pair"] == pair].copy()
        trades["open_date"] = pd.to_datetime(trades["open_date"], utc=True)
        trades["close_date"] = pd.to_datetime(trades["close_date"], utc=True)
        if date_from is not None:
            trades = trades[trades["close_date"] >= date_from].copy()
        if date_to is not None:
            trades = trades[trades["open_date"] <= date_to].copy()

    fig = go.Figure()
    if show_clusters:
        add_cluster_rectangles(fig, dataframe)
    fig.add_trace(
        go.Candlestick(
            x=dataframe["date"],
            open=dataframe["open"],
            high=dataframe["high"],
            low=dataframe["low"],
            close=dataframe["close"],
            name="K line",
        )
    )

    for column, color in MA_COLORS.items():
        fig.add_trace(
            go.Scatter(
                x=dataframe["date"],
                y=dataframe[column],
                mode="lines",
                name=column.upper(),
                line={"color": color, "width": 1.3},
            )
        )

    if not trades.empty:
        add_trade_markers(fig, trades[trades["is_short"] == False], is_short=False, is_entry=True)
        add_trade_markers(fig, trades[trades["is_short"] == False], is_short=False, is_entry=False)
        add_trade_markers(fig, trades[trades["is_short"] == True], is_short=True, is_entry=True)
        add_trade_markers(fig, trades[trades["is_short"] == True], is_short=True, is_entry=False)

    title = f"{strategy} {pair} {timeframe} full history"
    suffix = ""
    if date_from is not None or date_to is not None:
        from_label = date_from.strftime("%Y%m%d") if date_from is not None else "start"
        to_label = date_to.strftime("%Y%m%d") if date_to is not None else "end"
        suffix = f"-{from_label}-{to_label}"
        title = f"{strategy} {pair} {timeframe} {from_label} to {to_label}"
    fig.update_layout(
        title=title,
        template="plotly_white",
        xaxis_title="Date",
        yaxis_title="Price",
        height=900,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        xaxis_rangeslider_visible=False,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{pair_to_stem(pair)}-{timeframe}{suffix}-futures-trades.html"
    fig.write_html(output_file, include_plotlyjs="cdn")
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot futures backtest trades with six MA/EMA lines.")
    parser.add_argument("--backtest-zip", required=True, type=Path)
    parser.add_argument("--strategy", default="VideoDoubleMaFuturesStrategy")
    parser.add_argument("--data-dir", default=Path("user_data/data/gate/futures"), type=Path)
    parser.add_argument("--output-dir", default=Path("reports/futures_backtests/plots"), type=Path)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--pairs", nargs="+", default=["BTC/USDT:USDT", "ETH/USDT:USDT"])
    parser.add_argument("--date-from", default=None, help="Optional inclusive UTC start date, e.g. 2025-03-01")
    parser.add_argument("--date-to", default=None, help="Optional inclusive UTC end date, e.g. 2025-03-15")
    parser.add_argument("--hide-clusters", action="store_true", help="Do not draw MA cluster rectangles.")
    args = parser.parse_args()

    backtest = load_backtest(args.backtest_zip, args.strategy)
    date_from = parse_utc_date(args.date_from)
    date_to = parse_utc_date(args.date_to)
    for pair in args.pairs:
        output = plot_pair(
            args.data_dir,
            args.output_dir,
            backtest,
            args.strategy,
            pair,
            args.timeframe,
            date_from,
            date_to,
            show_clusters=not args.hide_clusters,
        )
        print(output)


if __name__ == "__main__":
    main()
