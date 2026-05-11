param(
    [string]$Timerange = "20210101-",
    [string]$Timeframes = "1h 4h",
    [string]$UserDir = "user_data",
    [string]$Config = "config\config_gate_dryrun.json",
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

$timeframeArgs = $Timeframes -split "\s+" | Where-Object { $_ -ne "" }
$argsList = @(
    "download-data",
    "--exchange", "gate",
    "--pairs", "BTC/USDT", "ETH/USDT",
    "--timeframes"
) + $timeframeArgs + @(
    "--userdir", $UserDir,
    "-c", $Config,
    "--timerange", $Timerange
)

& $FreqtradeExe @argsList
