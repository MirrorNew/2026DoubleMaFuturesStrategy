param(
    [string]$Timerange = "20210101-",
    [string]$Timeframe = "1h",
    [string]$UserDir = "user_data",
    [string]$Config = "config\config_gate_futures.json",
    [string]$Strategy = "VideoDoubleMaFuturesStrategy",
    [string]$BacktestDirectory = "",
    [string]$Notes = "",
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
    "backtesting",
    "--userdir", $UserDir,
    "-c", $Config,
    "--strategy", $Strategy,
    "--timeframe", $Timeframe,
    "--timerange", $Timerange,
    "--export", "trades"
)

if (-not [string]::IsNullOrWhiteSpace($BacktestDirectory)) {
    $argsList += @("--backtest-directory", $BacktestDirectory)
}

if (-not [string]::IsNullOrWhiteSpace($Notes)) {
    $argsList += @("--notes", $Notes)
}

& $FreqtradeExe @argsList
