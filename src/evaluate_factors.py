from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .factors import evaluate_factor_expression, load_factor_specs


def pair_to_filename(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_")


def load_ohlcv(data_dir: Path, pair: str, timeframe: str) -> pd.DataFrame:
    stem = f"{pair_to_filename(pair)}-{timeframe}"
    candidates = [
        data_dir / f"{stem}.feather",
        data_dir / f"{stem}.parquet",
        data_dir / f"{stem}.json",
        data_dir / f"{stem}.csv",
    ]
    existing = next((path for path in candidates if path.exists()), None)
    if existing is None:
        raise FileNotFoundError(f"No data file found for {pair} {timeframe} under {data_dir}")

    if existing.suffix == ".feather":
        frame = pd.read_feather(existing)
    elif existing.suffix == ".parquet":
        frame = pd.read_parquet(existing)
    elif existing.suffix == ".csv":
        frame = pd.read_csv(existing)
    else:
        raw = json.loads(existing.read_text(encoding="utf-8"))
        if raw and isinstance(raw[0], list):
            frame = pd.DataFrame(raw, columns=["date", "open", "high", "low", "close", "volume"])
        else:
            frame = pd.DataFrame(raw)

    frame.columns = [str(column).lower() for column in frame.columns]
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
        frame = frame.sort_values("date").reset_index(drop=True)
    return frame


def quantile_spread(factor: pd.Series, forward_return: pd.Series, bins: int = 5) -> float:
    sample = pd.DataFrame({"factor": factor, "forward_return": forward_return}).dropna()
    if len(sample) < bins * 20 or sample["factor"].nunique() < bins:
        return float("nan")

    labels = pd.qcut(sample["factor"], q=bins, labels=False, duplicates="drop")
    grouped = sample.groupby(labels, observed=True)["forward_return"].mean()
    if len(grouped) < 2:
        return float("nan")
    return float(grouped.iloc[-1] - grouped.iloc[0])


def evaluate_one_factor(
    pair: str,
    frame: pd.DataFrame,
    spec: Any,
    horizon: int,
) -> dict[str, Any]:
    factor = evaluate_factor_expression(spec.formula, frame)
    close = frame["close"].astype(float)
    forward_return = close.shift(-horizon) / close - 1
    sample = pd.DataFrame({"factor": factor, "forward_return": forward_return}).dropna()

    if sample.empty:
        ic = float("nan")
        coverage = 0.0
    else:
        ic = float(sample["factor"].corr(sample["forward_return"], method="spearman"))
        coverage = float(len(sample) / len(frame))

    spread = quantile_spread(factor, forward_return)
    if spec.direction == "lower_is_better":
        ic = -ic if np.isfinite(ic) else ic
        spread = -spread if np.isfinite(spread) else spread

    return {
        "pair": pair,
        "factor_name": spec.factor_name,
        "direction": spec.direction,
        "lookback": spec.lookback,
        "horizon": horizon,
        "spearman_ic": ic,
        "quantile_spread": spread,
        "coverage": coverage,
        "n_samples": int(len(sample)),
        "formula": spec.formula,
        "hypothesis": spec.hypothesis,
        "risk": spec.risk,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate candidate factors on Freqtrade OHLCV data.")
    parser.add_argument("--data-dir", required=True, help="Freqtrade data directory, for example user_data/data/gate.")
    parser.add_argument("--factors", default="factors/candidates.json", help="Candidate factor JSON file.")
    parser.add_argument("--output", default="reports/factor_report.csv", help="CSV report path.")
    parser.add_argument("--pairs", nargs="+", default=["BTC/USDT", "ETH/USDT"], help="Pairs to evaluate.")
    parser.add_argument("--timeframe", default="1h", help="Timeframe to evaluate.")
    parser.add_argument("--horizon", type=int, default=24, help="Forward return horizon in candles.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    raw_specs = json.loads(Path(args.factors).read_text(encoding="utf-8"))
    specs = load_factor_specs(raw_specs)

    rows: list[dict[str, Any]] = []
    for pair in args.pairs:
        frame = load_ohlcv(data_dir, pair, args.timeframe)
        for spec in specs:
            try:
                rows.append(evaluate_one_factor(pair, frame, spec, args.horizon))
            except Exception as exc:
                rows.append(
                    {
                        "pair": pair,
                        "factor_name": spec.factor_name,
                        "direction": spec.direction,
                        "lookback": spec.lookback,
                        "horizon": args.horizon,
                        "spearman_ic": float("nan"),
                        "quantile_spread": float("nan"),
                        "coverage": 0.0,
                        "n_samples": 0,
                        "formula": spec.formula,
                        "hypothesis": spec.hypothesis,
                        "risk": f"evaluation_error: {exc}",
                    }
                )

    report = pd.DataFrame(rows)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output, index=False, encoding="utf-8")

    summary = (
        report.groupby("factor_name", as_index=False)
        .agg(
            mean_ic=("spearman_ic", "mean"),
            mean_spread=("quantile_spread", "mean"),
            min_coverage=("coverage", "min"),
            total_samples=("n_samples", "sum"),
        )
        .sort_values("mean_ic", key=lambda series: series.abs(), ascending=False)
    )
    summary_path = output.with_name(output.stem + "_summary.csv")
    summary.to_csv(summary_path, index=False, encoding="utf-8")

    print(f"Wrote factor report to {output}")
    print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
