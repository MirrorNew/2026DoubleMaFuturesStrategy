param(
    [string]$PythonExe = $env:LOCAL_PYTHON_EXE
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = "E:\my_evns\py312_torch28\python.exe"
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

& $PythonExe -m pip install -U pip
& $PythonExe -m pip install -r requirements-research.txt
