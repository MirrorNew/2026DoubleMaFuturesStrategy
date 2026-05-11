from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .factors import FALLBACK_FACTOR_SPECS


PROMPT = """Generate 8 candidate alpha factors for BTC/USDT and ETH/USDT 1h OHLCV data.

Constraints:
- Return only a JSON array.
- Do not include markdown.
- Each item must include: factor_name, hypothesis, formula, direction, lookback, risk.
- Formula may only use these names: open, high, low, close, volume.
- Formula may only use these functions:
  sma(series, window), ema(series, window), rsi(close, window),
  atr(high, low, close, window), pct_change(series, periods),
  log_return(close, periods), zscore(series, window),
  rolling_min(series, window), rolling_max(series, window),
  rolling_std(series, window), abs(value), min(a, b), max(a, b).
- Do not use future returns, labels, shift with negative periods, order book data, funding rates, news, or account state.
- Prefer simple momentum, trend quality, volatility regime, range breakout, and volume confirmation hypotheses.
- Each factor must be computable from candles available at the current closed bar.
"""


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        raise ValueError("LLM response did not contain a JSON array.")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError("LLM response JSON must be an array.")
    return parsed


def mine_with_llm() -> list[dict[str, Any]]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install openai or use the fallback factors.") from exc

    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY, DEEPSEEK_API_KEY, or OPENAI_API_KEY is not set.")

    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("LLM_MODEL", "deepseek-v4-pro")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system","content": "You are a quantitative research assistant. Output only valid JSON.",},
            {"role": "user", "content": PROMPT},
        ],
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}}
    )
    content = response.choices[0].message.content or ""
    return _extract_json_array(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate candidate factor JSON with an LLM or fallback list.")
    parser.add_argument("--out", default="factors/candidates.json", help="Output JSON file.")
    parser.add_argument("--fallback", action="store_true", help="Skip LLM API and write built-in candidates.")
    args = parser.parse_args()

    load_dotenv()
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.fallback:
        factors = FALLBACK_FACTOR_SPECS
    else:
        try:
            factors = mine_with_llm()
        except Exception as exc:
            print(f"LLM mining failed, writing fallback factors instead: {exc}")
            factors = FALLBACK_FACTOR_SPECS

    output_path.write_text(json.dumps(factors, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(factors)} candidate factors to {output_path}")


if __name__ == "__main__":
    main()
