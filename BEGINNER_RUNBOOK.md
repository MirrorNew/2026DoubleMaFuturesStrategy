# 新手运行手册：LLM 因子挖掘 + Freqtrade 回测

这份文档假设你已经配置好了 PyCharm，并且你的研究 Python 是：

```text
E:\my_evns\py312_torch28\python.exe
```

先记住一个核心区别：

- `py312_torch28`：跑 LLM 因子挖掘、pandas 因子评估、报告生成。
- `freqtrade` 环境：下载行情数据、运行 Freqtrade 回测、做 lookahead/recursive 审计。

不要把 Freqtrade 装进 `py312_torch28`。Freqtrade 依赖比较重，单独环境更稳。

## 0. 项目根目录

你写命令时，先进入这个目录：

```powershell
cd D:\LLM-CodexProject\trade\llm_freqtrade_factor_lab
```

后面的相对路径都以这个目录为准。

## 1. 安装研究脚本依赖

这一步使用你的本地 Anaconda Python：

```powershell
.\scripts\install_research_deps.ps1
```

等价于：

```powershell
E:\my_evns\py312_torch28\python.exe -m pip install -r requirements-research.txt
```

安装完成后，PyCharm 里可以运行：

```text
src/llm_factor_miner.py
src/evaluate_factors.py
```

## 2. 安装 Freqtrade

Freqtrade 官方文档对 Windows 的建议是：Docker / WSL2 通常更顺；如果原生 Windows 安装，优先用它仓库里的 `setup.ps1`。

如果你想沿用 Anaconda，可以新建一个独立环境：

```powershell
conda create --name freqtrade python=3.12
conda activate freqtrade
cd D:\LLM-CodexProject\trade
git clone https://github.com/freqtrade/freqtrade.git
cd freqtrade
git checkout stable
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
freqtrade --version
```

如果上面的依赖安装失败，可以改用官方 Windows 脚本：

```powershell
cd D:\LLM-CodexProject\trade\freqtrade
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
. .\setup.ps1
freqtrade --version
```

注意：之后每次要用 Freqtrade，都先打开 Anaconda Prompt 或 PowerShell，然后：

```powershell
conda activate freqtrade
cd D:\LLM-CodexProject\trade\llm_freqtrade_factor_lab
```

## 3. 整个流程怎么跑

### 第一步：生成候选因子

没有 API Key 时，先用内置候选因子跑通：

```powershell
.\scripts\mine_factors.ps1 -Fallback
```

它会生成：

```text
factors/candidates.json
```

如果你配置了 DeepSeek/OpenAI 兼容 API，就复制 `.env.example` 为 `.env`，填入：

```text
LLM_API_KEY=你的key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

然后运行：

```powershell
.\scripts\mine_factors.ps1
```

这一步只是生成候选因子，不会交易。

### 第二步：下载 Freqtrade 行情数据

这一步必须在 `freqtrade` 环境中执行：

```powershell
conda activate freqtrade
cd D:\LLM-CodexProject\trade\llm_freqtrade_factor_lab
.\scripts\download_data.ps1 -Timerange 20210101- -Timeframes "1h 4h"
```

它会下载 Gate 的：

```text
BTC/USDT
ETH/USDT
```

数据通常会出现在：

```text
user_data/data/gate
```

### 第三步：离线评估候选因子

这一步回到研究 Python，也就是 `py312_torch28`：

```powershell
.\scripts\evaluate_factors.ps1
```

输出文件：

```text
reports/factor_report.csv
reports/factor_report_summary.csv
```

你可以用 Excel、PyCharm、pandas 打开看。

重点看：

- `spearman_ic`：因子和未来收益的秩相关，不要期待很大。
- `quantile_spread`：高因子组和低因子组的未来收益差。
- `coverage`：有效样本覆盖率。
- `n_samples`：样本数。

这一步会使用未来收益作为“研究标签”，但它只用于离线评估，不能进入实盘策略。

### 第四步：运行 Freqtrade 固定策略回测

仍然在 `freqtrade` 环境：

```powershell
conda activate freqtrade
cd D:\LLM-CodexProject\trade\llm_freqtrade_factor_lab
.\scripts\backtest.ps1 -Timerange 20210101-
```

它会运行：

```text
user_data/strategies/LlmFactorBtcEthStrategy.py
```

这个策略不会调用 LLM。它只使用固定公式算出来的趋势、动量、成交量、波动过滤。

### 第五步：检查有没有未来函数

```powershell
.\scripts\audit_strategy.ps1 -Timerange 20210101-
```

这一步会运行：

- `lookahead-analysis`
- `recursive-analysis`

如果这两个不过，不要相信回测结果。

## 4. PyCharm 里怎么跑

PyCharm 更适合跑研究脚本，不适合直接管理 Freqtrade 全流程。

建议你在 PyCharm 里这样做：

1. Interpreter 选择：

```text
E:\my_evns\py312_torch28\python.exe
```

2. Working directory 选择：

```text
D:\LLM-CodexProject\trade\llm_freqtrade_factor_lab
```

3. 先运行：

```text
src/llm_factor_miner.py
```

参数可以填：

```text
--out factors/candidates.json --fallback
```

4. 再运行：

```text
src/evaluate_factors.py
```

参数填：

```text
--data-dir user_data\data\gate --factors factors\candidates.json --output reports\factor_report.csv
```

前提是你已经用 Freqtrade 下载好了数据。

## 5. 你应该如何理解这些脚本

脚本不是另一种编程语言负担，它只是把长命令保存起来。

例如：

```powershell
.\scripts\mine_factors.ps1 -Fallback
```

本质上是在帮你执行：

```powershell
E:\my_evns\py312_torch28\python.exe -m src.llm_factor_miner --out factors\candidates.json --fallback
```

再比如：

```powershell
.\scripts\backtest.ps1
```

本质上是在帮你执行：

```powershell
freqtrade backtesting --userdir user_data -c config\config_gate_dryrun.json --strategy LlmFactorBtcEthStrategy --timerange 20210101- --export trades
```

所以你可以把 `.ps1` 理解成“可重复点击/运行的命令模板”。

## 6. 最推荐的第一次完整运行

按这个顺序来：

```powershell
cd D:\LLM-CodexProject\trade\llm_freqtrade_factor_lab
.\scripts\install_research_deps.ps1
.\scripts\mine_factors.ps1 -Fallback
```

然后进入 Freqtrade 环境：

```powershell
conda activate freqtrade
cd D:\LLM-CodexProject\trade\llm_freqtrade_factor_lab
.\scripts\download_data.ps1 -Timerange 20210101- -Timeframes "1h 4h"
.\scripts\backtest.ps1 -Timerange 20210101-
.\scripts\audit_strategy.ps1 -Timerange 20210101-
```

最后回到研究脚本：

```powershell
.\scripts\evaluate_factors.ps1
```

如果中间任何一步报错，先看报错最底部 5 到 10 行，通常那里才是真正原因。
