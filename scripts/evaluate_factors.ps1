param(
    [string]$DataDir = "user_data\data\gate",
    [string]$Factors = "factors\candidates.json",
    [string]$Output = "reports\factor_report.csv",
    [string]$Timeframe = "1h",
    [int]$Horizon = 24,
    [string]$PythonExe = $env:LOCAL_PYTHON_EXE
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = "E:\my_evns\py312_torch28\python.exe"
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

& $PythonExe -m src.evaluate_factors `
    --data-dir $DataDir `
    --factors $Factors `
    --output $Output `
    --timeframe $Timeframe `
    --horizon $Horizon
