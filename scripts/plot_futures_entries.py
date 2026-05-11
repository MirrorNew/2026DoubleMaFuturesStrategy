from __future__ import annotations

import argparse
import sys
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


def pair_to_stem(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_")


def find_data_file(data_dir: Path, pair: str, timeframe: str) -> Path:
    stem = pair_to_stem(pair)
    candidates = sorted(data_dir.glob(f"{stem}-{timeframe}*.feather"))
    if not candidates:
        raise FileNotFoundError(f"No feather data found for {pair} {timeframe} in {data_dir}")
    futures_files = [path for path in candidates if path.name.endswith("-futures.feather")]
    return futures_files[0] if futures_files else candidates[0]


def build_signal_dataframe(data_file: Path, pair: str) -> pd.DataFrame:
    strategy = VideoDoubleMaFuturesStrategy({})
    dataframe = pd.read_feather(data_file)
    dataframe["date"] = pd.to_datetime(dataframe["date"], utc=True)
    dataframe = strategy.populate_indicators(dataframe, {"pair": pair})
    dataframe = strategy.populate_entry_trend(dataframe, {"pair": pair})
    return dataframe


def add_entry_markers(fig: go.Figure, dataframe: pd.DataFrame, column: str, name: str, color: str, symbol: str) -> None:
    signals = dataframe[dataframe[column].fillna(0).astype(bool)]
    if signals.empty:
        return

    hover = []
    for row in signals.to_dict("records"):
        hover.append(
            f"{name}<br>"
            f"{row['date']}<br>"
            f"close: {row['close']:.4f}<br>"
            f"tag: {row.get('enter_tag', '')}<br>"
            f"ma_width: {row.get('ma_width', float('nan')):.4%}"
        )

    fig.add_trace(
        go.Scatter(
            x=signals["date"],
            y=signals["close"],
            mode="markers",
            name=name,
            marker={"color": color, "symbol": symbol, "size": 10, "line": {"width": 1, "color": "#111827"}},
            text=hover,
            hovertemplate="%{text}<extra></extra>",
        )
    )


def plot_entries(dataframe: pd.DataFrame, output_file: Path, pair: str, timeframe: str) -> None:
    fig = go.Figure()
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

    add_entry_markers(fig, dataframe, "enter_long", "Long entry signal", "#16a34a", "triangle-up")
    add_entry_markers(fig, dataframe, "enter_short", "Short entry signal", "#dc2626", "triangle-down")

    fig.update_layout(
        title=f"{pair} {timeframe} entry signals only",
        template="plotly_white",
        xaxis_title="Date",
        yaxis_title="Price",
        height=900,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        xaxis_rangeslider_visible=False,
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(output_file, include_plotlyjs="cdn")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot strategy entry signals without running backtesting.")
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--pairs", nargs="+", default=["BTC/USDT:USDT", "ETH/USDT:USDT"])
    parser.add_argument("--data-dir", default=Path("user_data/data/gate/futures"), type=Path)
    parser.add_argument("--output-dir", default=Path("reports/futures_backtests/entry_signals"), type=Path)
    args = parser.parse_args()

    for pair in args.pairs:
        data_file = find_data_file(args.data_dir, pair, args.timeframe)
        dataframe = build_signal_dataframe(data_file, pair)
        output_file = args.output_dir / f"{pair_to_stem(pair)}-{args.timeframe}-entry-signals.html"
        plot_entries(dataframe, output_file, pair, args.timeframe)
        long_count = int(dataframe.get("enter_long", pd.Series(dtype=float)).fillna(0).sum())
        short_count = int(dataframe.get("enter_short", pd.Series(dtype=float)).fillna(0).sum())
        print(f"{output_file} | long={long_count} short={short_count}")


if __name__ == "__main__":
    main()
