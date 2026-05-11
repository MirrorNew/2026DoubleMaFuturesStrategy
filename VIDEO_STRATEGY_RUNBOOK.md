# 视频双均线策略运行手册

## 环境

Anaconda 实际路径：

```powershell
E:\anaconda3\Scripts\conda.exe
```

激活环境：

```powershell
& 'E:\anaconda3\shell\condabin\conda-hook.ps1'
conda activate env_freqtrade
cd D:\LLM-CodexProject\trade\llm_freqtrade_factor_lab
```

Freqtrade 可执行文件：

```powershell
E:\my_evns\env_freqtrade\Scripts\freqtrade.exe
```

如果 PowerShell 拦截脚本执行，用下面这种一次性方式运行，不需要修改系统执行策略：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backtest.ps1
```

## 下载数据

```powershell
.\scripts\download_data.ps1 -Timerange 20210101- -Timeframes "1h 4h"
```

当前配置下载 Gate 的：

```text
BTC/USDT
ETH/USDT
```

当前数据状态：

- `BTC/USDT`、`ETH/USDT` 的 `4h` 数据已下载到 2022-01-01 以后。
- `BTC/USDT`、`ETH/USDT` 的 `1h` 数据已下载到 2025-04-01 以后。
- Gate 对历史 K 线有约 10000 根限制，因此较小周期不能一次性拉太久。

## 回测

```powershell
.\scripts\backtest.ps1 -Strategy VideoDoubleMaStrategy -Timerange 20210101-
```

## 反作弊审计

```powershell
.\scripts\audit_strategy.ps1 -Strategy VideoDoubleMaStrategy -Timerange 20210101-
```

如果 `lookahead-analysis` 或 `recursive-analysis` 不通过，不要相信回测结果。

## 当前回测结论

`VideoDoubleMaStrategy` 是按视频规则机械化后的第一版，不建议实盘。

4h 回测结果：

- 总收益率：-49.53%
- 交易次数：472
- 胜率：53.6%
- Profit factor：0.63
- 最大回撤：57.32%

偏差审计没有发现 lookahead bias，但这只说明代码没有明显偷看未来，并不说明策略有盈利能力。详细漏洞和下一轮修复建议见：

```text
reports\video_vdCdg4MdwBs\backtest_findings.md
```

## 合约多空版

新增合约策略：

```text
user_data\strategies\VideoDoubleMaFuturesStrategy.py
```

新增合约配置：

```text
config\config_gate_futures.json
```

注意：原计划优先 Gate `cross futures`，但 Freqtrade 2026.4 明确不支持 Gate 的 cross futures，因此当前配置已降级为 `isolated futures`。每笔保证金仍为 `100 USDT`，策略杠杆回调仍尝试使用 `100x`。当前已按人工操作习惯设置 `max_open_trades = 1`，同一时间只允许一个仓位。

常用命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\download_futures_data.ps1 -Timerange 20250401- -Timeframes "1h"
powershell -ExecutionPolicy Bypass -File .\scripts\download_futures_data.ps1 -Timerange 20220101- -Timeframes "4h"
powershell -ExecutionPolicy Bypass -File .\scripts\backtest_futures.ps1 -Timeframe 1h -Timerange 20250401-
powershell -ExecutionPolicy Bypass -File .\scripts\backtest_futures.ps1 -Timeframe 4h -Timerange 20220101-
```

只画开仓信号、不跑回测：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\plot_futures_entries.ps1 -Timeframe 1h
powershell -ExecutionPolicy Bypass -File .\scripts\plot_futures_entries.ps1 -Timeframe 4h
```

合约版结果报告：

```text
reports\futures_backtests\futures_backtest_report.md
```

## PyCharm 使用提示

- 打开项目目录：`D:\LLM-CodexProject\trade\llm_freqtrade_factor_lab`。
- Interpreter 选择：`E:\my_evns\env_freqtrade\python.exe`。
- 编辑策略文件：`user_data\strategies\VideoDoubleMaStrategy.py`。
- 改参数优先改这些类变量：
  - `timeframe`
  - `ma_cluster_width_threshold`
  - `cluster_lookback`
  - `pullback_window`
  - `breakout_buffer`
  - `pullback_touch_tolerance`
- 如果你想从 `4h` 改成 `1h`，先确认已经下载 `1h` 数据，然后把策略里的 `timeframe = "4h"` 改成 `timeframe = "1h"`。
- 不要在策略里使用未来数据，例如 `shift(-1)`、未来收益、整段数据全局最大/最小值。
