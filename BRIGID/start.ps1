
param(
    [switch]$WithBackend
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "   BRIGID RTLS Desktop Platform"       -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

if ($WithBackend) {
    Write-Host "[*] Starting Python backend..." -ForegroundColor Yellow
    $backendDir = Join-Path $root "backend"
    Start-Process -NoNewWindow powershell -ArgumentList "-Command", "cd '$backendDir'; python -m uvicorn main:app --reload --port 8000"
    Start-Sleep -Seconds 2
    Write-Host "[+] Backend started on http://localhost:8000" -ForegroundColor Green
    Write-Host ""
}

Write-Host "[*] Starting Electron frontend..." -ForegroundColor Yellow
$frontendDir = Join-Path $root "frontend"
Push-Location $frontendDir

try {
    npm run dev
} finally {
    Pop-Location
}
