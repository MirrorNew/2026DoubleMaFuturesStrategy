param(
    [string]$Timeframe = "1h",
    [string]$Pairs = "BTC/USDT:USDT ETH/USDT:USDT",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    if (Test-Path -LiteralPath "E:\my_evns\env_freqtrade\python.exe") {
        $PythonExe = "E:\my_evns\env_freqtrade\python.exe"
    } else {
        throw "python.exe not found. Activate env_freqtrade or pass -PythonExe."
    }
}

$pairArgs = $Pairs -split "\s+" | Where-Object { $_ -ne "" }
$argsList = @(
    "scripts\plot_futures_entries.py",
    "--timeframe", $Timeframe,
    "--pairs"
) + $pairArgs

& $PythonExe @argsList
