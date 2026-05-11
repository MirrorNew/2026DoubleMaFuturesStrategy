param(
    [string]$OutFile = "factors\candidates.json",
    [string]$PythonExe = $env:LOCAL_PYTHON_EXE,
    [switch]$Fallback
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = "E:\my_evns\py312_torch28\python.exe"
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

if ($Fallback) {
    & $PythonExe -m src.llm_factor_miner --out $OutFile --fallback
} else {
    & $PythonExe -m src.llm_factor_miner --out $OutFile
}
