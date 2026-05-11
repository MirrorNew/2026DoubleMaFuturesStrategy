param(
    [string]$Timerange = "20210101-",
    [string]$UserDir = "user_data",
    [string]$Config = "config\config_gate_dryrun.json",
    [string]$Strategy = "VideoDoubleMaStrategy",
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

$argsList = @(
    "backtesting",
    "--userdir", $UserDir,
    "-c", $Config,
    "--strategy", $Strategy,
    "--timerange", $Timerange,
    "--export", "trades"
)

& $FreqtradeExe @argsList
