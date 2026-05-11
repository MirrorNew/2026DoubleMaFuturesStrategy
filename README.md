# LLM Factor Lab for BTC/ETH + Freqtrade

这个子项目用于把“LLM 生成候选因子”与 “Freqtrade 可复现回测”分开：

- LLM 只负责提出候选因子假设和公式。
- `src/factors.py` 只允许白名单函数计算因子，拒绝任意代码执行。
- `src/evaluate_factors.py` 用历史 OHLCV 做 IC、分组收益和覆盖率评估。
- `user_data/strategies/LlmFactorBtcEthStrategy.py` 是固定、可审计的 Freqtrade 策略。
- `scripts/audit_strategy.ps1` 运行 Freqtrade 的 lookahead / recursive 分析。

这不是投资建议，也不是“稳赚策略”。这里的目标是建立一个不容易自欺欺人的研究和回测闭环。

## 目录

```text
llm_freqtrade_factor_lab/
  BEGINNER_RUNBOOK.md
  config/
    config_gate_dryrun.json
  factors/
    candidates.example.json
  reports/
    .gitkeep
  scripts/
    audit_strategy.ps1
    backtest.ps1
    download_data.ps1
    mine_factors.ps1
  src/
    __init__.py
    evaluate_factors.py
    factors.py
    llm_factor_miner.py
  user_data/
    strategies/
      LlmFactorBtcEthStrategy.py
  .env.example
  requirements-research.txt
  strategy_confidence_checklist.md
```

## 推荐环境

如果你第一次跑这个项目，先读：

```text
BEGINNER_RUNBOOK.md
```

Freqtrade 建议单独环境安装，不要和 PyTorch / Notebook 环境混装。

```powershell
conda create --name freqtrade python=3.12
conda activate freqtrade
pip install freqtrade
```

研究脚本依赖：

```powershell
.\scripts\install_research_deps.ps1
```

如果你要明确使用本机 Anaconda 环境，可以直接指定：

```powershell
.\scripts\install_research_deps.ps1 -PythonExe E:\my_evns\py312_torch28\python.exe
```

IDEA / PyCharm 里建议把 Project Interpreter 设成：

```text
E:\my_evns\py312_torch28\python.exe
```

然后把运行配置的 Working directory 设为：

```text
D:\LLM-CodexProject\trade\llm_freqtrade_factor_lab
```

如果使用 `.env`，添加：

```text
LOCAL_PYTHON_EXE=E:\my_evns\py312_torch28\python.exe
```

如果使用 DeepSeek 或 OpenAI 兼容 API，复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

然后填写：

```text
LLM_API_KEY=...
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

没有 API Key 也可以运行，脚本会输出内置的保守候选因子。

## 1. 下载 BTC/ETH 数据

在 `llm_freqtrade_factor_lab` 目录下运行：

```powershell
.\scripts\download_data.ps1 -Timerange 20210101- -Timeframes "1h 4h"
```

等价的 Freqtrade 命令大致是：

```powershell
freqtrade download-data --exchange gate --pairs BTC/USDT ETH/USDT --timeframes 1h 4h --userdir user_data --timerange 20210101-
```

## 2. 运行固定策略回测

```powershell
.\scripts\backtest.ps1 -Timerange 20210101-
```

回测策略文件：

```text
user_data/strategies/LlmFactorBtcEthStrategy.py
```

它使用固定的动量、趋势、成交量、波动过滤因子，不会在回测过程中调用 LLM。

## 3. 做反作弊审计

```powershell
.\scripts\audit_strategy.ps1 -Timerange 20210101-
```

审计包括：

- `lookahead-analysis`：检查未来函数 / 数据泄漏。
- `recursive-analysis`：检查指标是否因为启动窗口不足或递归计算产生不稳定结果。

只有这两个检查通过，才允许进入下一轮策略比较。

## 4. 让 LLM 生成候选因子

```powershell
.\scripts\mine_factors.ps1 -OutFile factors\candidates.json
```

候选因子 JSON 格式：

```json
[
  {
    "factor_name": "volume_adjusted_momentum_24",
    "hypothesis": "Momentum is more reliable when confirmed by volume expansion.",
    "formula": "zscore(pct_change(close, 24), 120) * zscore(volume / sma(volume, 20), 120)",
    "direction": "higher_is_better",
    "lookback": 120,
    "risk": "Can chase late-stage trends unless paired with volatility filters."
  }
]
```

公式只允许使用 `src/factors.py` 里的白名单函数，例如：

- `sma(series, window)`
- `ema(series, window)`
- `rsi(close, window)`
- `atr(high, low, close, window)`
- `pct_change(series, periods)`
- `log_return(close, periods)`
- `zscore(series, window)`
- `rolling_min(series, window)`
- `rolling_max(series, window)`
- `rolling_std(series, window)`

## 5. 评估候选因子

Freqtrade 下载数据后，运行：

```powershell
.\scripts\evaluate_factors.ps1 -DataDir user_data\data\gate -Factors factors\candidates.json -Output reports\factor_report.csv
```

输出包括：

- Spearman IC
- top-bottom 分组收益差
- 覆盖率
- 方向一致性
- 每个交易对的样本数

注意：这里会使用未来收益作为研究标签，但该标签只用于离线评估，不能进入 Freqtrade 策略指标。

## 6. 下一步怎么把因子放入策略

不要自动把 LLM 生成的最高收益因子塞进策略。正确流程是：

1. 候选因子通过白名单公式解析。
2. 至少跨 BTC 和 ETH 两个币种评估。
3. 做样本内 / 样本外切分。
4. 通过 `lookahead-analysis` 和 `recursive-analysis`。
5. 与买入持有、固定策略、低换手策略比较。
6. 只把稳定因子作为过滤器或仓位调整项，不直接替代风控。

## 关键参考

- Freqtrade 文档：<https://docs.freqtrade.io/en/stable/>
- Freqtrade 策略定制：<https://docs.freqtrade.io/en/stable/strategy-customization/>
- Freqtrade 回测：<https://docs.freqtrade.io/en/stable/backtesting/>
- Freqtrade lookahead-analysis：<https://docs.freqtrade.io/en/stable/lookahead-analysis/>
