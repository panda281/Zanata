# Windows PowerShell wrapper for zanata_replace_keyword.py
# Usage:
#   .\scripts\zanata_replace_keyword.ps1 -Find "HelloCash" -Replace "VitaBirr" -DryRun
# Or pass through native args:
#   .\scripts\zanata_replace_keyword.ps1 --find "HelloCash" --replace "VitaBirr" --dry-run

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyScript = Join-Path $ScriptDir "zanata_replace_keyword.py"

function Invoke-ZanataReplace {
    param([string[]]$PythonArgs)

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 $PyScript @PythonArgs
        exit $LASTEXITCODE
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python $PyScript @PythonArgs
        exit $LASTEXITCODE
    }

    Write-Error "Python 3 was not found. Install Python 3 and ensure 'py' or 'python' is on PATH."
    exit 1
}

Invoke-ZanataReplace -PythonArgs $Args
