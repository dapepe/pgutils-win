param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$cliPath = Join-Path $rootDir "cli.py"
$venvDir = Join-Path $rootDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirements = Join-Path $rootDir "requirements.txt"

function Ensure-Venv {
    param(
        [string]$VenvDir,
        [string]$VenvPython,
        [string]$Requirements
    )

    if (-not (Test-Path $Requirements)) {
        Write-Error "requirements.txt not found at $Requirements"
        exit 1
    }

    if (-not (Test-Path $VenvPython)) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv $VenvDir
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv $VenvDir
        } else {
            Write-Error "Python not found in PATH. Install Python 3 or use the Python launcher (py)."
            exit 1
        }

        if (-not (Test-Path $VenvPython)) {
            Write-Error "Failed to create virtual environment at $VenvDir"
            exit 1
        }
    }

    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $VenvPython -c "import typer, rich" 2>$null | Out-Null
    $probeExit = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorAction

    if ($probeExit -ne 0) {
        & $VenvPython -m pip install -r $Requirements
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install dependencies from $Requirements"
            exit $LASTEXITCODE
        }
    }
}

Ensure-Venv -VenvDir $venvDir -VenvPython $venvPython -Requirements $requirements
& $venvPython $cliPath @CliArgs
exit $LASTEXITCODE
