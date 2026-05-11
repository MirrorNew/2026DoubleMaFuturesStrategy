param(
    [string]$Timerange = "20210101-",
    [string]$Timeframe = "1h",
    [string]$UserDir = "user_data",
    [string]$Config = "config\config_gate_futures.json",
    [string]$Strategy = "VideoDoubleMaFuturesStrategy",
    [string]$BacktestFilename = "",
    [int]$PlotLimit = 20000,
    [string]$FreqtradeExe = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($FreqtradeExe)) {
    $cmd = Get-Command freqtrade -ErrorAction SilentlyContinue
    if ($cmd) {
        $FreqtradeExe = $cmd.Source
    } elseif (Test-Path -LiteralPath "E:\my_evns\env_freqtrade\Scripts\freqtrade.exe") {
        $FreqtradeExe = "E:\my_evns\env_freqtrade\Scripts\freqtrade.exe"
    } else {
        throw "freqtrade.exe not found. Activate env_freqtrade or pass -FreqtradeExe."
    }
}

$env:HTTP_PROXY = "http://127.0.0.1:7897"
$env:HTTPS_PROXY = "http://127.0.0.1:7897"

$argsList = @(
    "plot-dataframe",
    "--userdir", $UserDir,
    "-c", $Config,
    "--strategy", $Strategy,
    "--timeframe", $Timeframe,
    "--timerange", $Timerange,
    "--pairs", "BTC/USDT:USDT", "ETH/USDT:USDT",
    "--indicators1", "ma_5", "ma_10", "ma_30", "ema_5", "ema_10", "ema_30",
    "--plot-limit", "$PlotLimit",
    "--trade-source", "file"
)

if (-not [string]::IsNullOrWhiteSpace($BacktestFilename)) {
    $argsList += @("--backtest-filename", $BacktestFilename)
}

& $FreqtradeExe @argsList
