$ErrorActionPreference = "Stop"
Push-Location (Join-Path $PSScriptRoot "backend")
try {
    python -c "import db; db.init_db(reset=True)"
    Write-Host "MIRAGE-X demo data reset."
}
finally {
    Pop-Location
}
