from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FactorSpec:
    factor_name: str
    hypothesis: str
    formula: str
    direction: str = "higher_is_better"
    lookback: int = 120
    risk: str = ""


FALLBACK_FACTOR_SPECS: list[dict[str, Any]] = [
    {
        "factor_name": "volume_adjusted_momentum_24",
        "hypothesis": "Momentum is more reliable when confirmed by volume expansion.",
        "formula": "zscore(pct_change(close, 24), 120) * zscore(volume / sma(volume, 20), 120)",
        "direction": "higher_is_better",
        "lookback": 120,
        "risk": "Can chase late-stage trends unless paired with volatility filters.",
    },
    {
        "factor_name": "trend_quality_12_48",
        "hypothesis": "A fast EMA above a slow EMA is more useful when volatility is not extreme.",
        "formula": "zscore(ema(close, 12) / ema(close, 48) - 1, 120) / (abs(zscore(atr(high, low, close, 14) / close, 120)) + 1)",
        "direction": "higher_is_better",
        "lookback": 120,
        "risk": "EMA factors may degrade in choppy range-bound markets.",
    },
    {
        "factor_name": "range_breakout_48",
        "hypothesis": "Breakouts near the recent range high are more meaningful when accompanied by high volume.",
        "formula": "zscore(close / rolling_max(close, 48) - 1, 120) * zscore(volume, 120)",
        "direction": "higher_is_better",
        "lookback": 120,
        "risk": "Breakout factors can suffer during false breakouts and news spikes.",
    },
]


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(int(window), min_periods=int(window)).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=int(window), adjust=False, min_periods=int(window)).mean()


def pct_change(series: pd.Series, periods: int = 1) -> pd.Series:
    return series.pct_change(int(periods))


def log_return(close: pd.Series, periods: int = 1) -> pd.Series:
    return np.log(close / close.shift(int(periods)))


def zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(int(window), min_periods=int(window)).mean()
    std = series.rolling(int(window), min_periods=int(window)).std(ddof=0)
    return (series - mean) / std.replace(0, np.nan)


def rolling_min(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(int(window), min_periods=int(window)).min()


def rolling_max(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(int(window), min_periods=int(window)).max()


def rolling_std(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(int(window), min_periods=int(window)).std(ddof=0)


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    avg_gain = up.ewm(alpha=1 / int(window), adjust=False, min_periods=int(window)).mean()
    avg_loss = down.ewm(alpha=1 / int(window), adjust=False, min_periods=int(window)).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / int(window), adjust=False, min_periods=int(window)).mean()


def safe_abs(value: pd.Series | float | int) -> pd.Series | float:
    if isinstance(value, pd.Series):
        return value.abs()
    return abs(value)


def safe_min(left: pd.Series | float | int, right: pd.Series | float | int) -> pd.Series | float:
    return np.minimum(left, right)


def safe_max(left: pd.Series | float | int, right: pd.Series | float | int) -> pd.Series | float:
    return np.maximum(left, right)


ALLOWED_FUNCTIONS = {
    "sma": sma,
    "ema": ema,
    "pct_change": pct_change,
    "log_return": log_return,
    "zscore": zscore,
    "rolling_min": rolling_min,
    "rolling_max": rolling_max,
    "rolling_std": rolling_std,
    "rsi": rsi,
    "atr": atr,
    "abs": safe_abs,
    "min": safe_min,
    "max": safe_max,
}

ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
    ast.UAdd,
)


def normalize_ohlcv(dataframe: pd.DataFrame) -> pd.DataFrame:
    rename = {column: str(column).lower() for column in dataframe.columns}
    normalized = dataframe.rename(columns=rename).copy()
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(normalized.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
    return normalized


def _validate_formula_ast(tree: ast.AST, allowed_names: set[str]) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_AST_NODES):
            raise ValueError(f"Disallowed syntax in formula: {type(node).__name__}")

        if isinstance(node, ast.Name) and node.id not in allowed_names:
            raise ValueError(f"Unknown name in formula: {node.id}")

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct function calls are allowed.")
            if node.func.id not in ALLOWED_FUNCTIONS:
                raise ValueError(f"Function is not allowed: {node.func.id}")
            if node.keywords:
                raise ValueError("Keyword arguments are not allowed in factor formulas.")


def evaluate_factor_expression(expression: str, dataframe: pd.DataFrame) -> pd.Series:
    normalized = normalize_ohlcv(dataframe)
    local_env: dict[str, Any] = {
        "open": normalized["open"],
        "high": normalized["high"],
        "low": normalized["low"],
        "close": normalized["close"],
        "volume": normalized["volume"],
        **ALLOWED_FUNCTIONS,
    }
    allowed_names = set(local_env)

    tree = ast.parse(expression, mode="eval")
    _validate_formula_ast(tree, allowed_names)
    value = eval(compile(tree, "<factor_formula>", "eval"), {"__builtins__": {}}, local_env)

    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        value = pd.Series(float(value), index=normalized.index)
    if not isinstance(value, pd.Series):
        raise ValueError("Factor formula must return a pandas Series.")

    return value.replace([np.inf, -np.inf], np.nan)


def load_factor_specs(raw_specs: list[dict[str, Any]]) -> list[FactorSpec]:
    specs: list[FactorSpec] = []
    for raw in raw_specs:
        specs.append(
            FactorSpec(
                factor_name=str(raw["factor_name"]),
                hypothesis=str(raw.get("hypothesis", "")),
                formula=str(raw["formula"]),
                direction=str(raw.get("direction", "higher_is_better")),
                lookback=int(raw.get("lookback", 120)),
                risk=str(raw.get("risk", "")),
            )
        )
    return specs
