param(
    [string]$Timerange = "20210101-",
    [string]$Timeframes = "1h 4h",
    [string]$UserDir = "user_data",
    [string]$Config = "config\config_gate_futures.json",
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

$timeframeArgs = $Timeframes -split "\s+" | Where-Object { $_ -ne "" }
$argsList = @(
    "download-data",
    "--exchange", "gate",
    "--trading-mode", "futures",
    "--pairs", "BTC/USDT:USDT", "ETH/USDT:USDT",
    "--timeframes"
) + $timeframeArgs + @(
    "--userdir", $UserDir,
    "-c", $Config,
    "--timerange", $Timerange
)

& $FreqtradeExe @argsList
