<#
.SYNOPSIS
    End-to-end verification of the built Windows setup program.

.DESCRIPTION
    Installs the application silently into build\verify-installer, checks the
    files, registry entries and shortcuts, launches the packaged application,
    then uninstalls it again and verifies the cleanup.

    Run after packaging\build_windows.ps1:

        pwsh -File packaging\verify_installer.ps1

    NOTE: this must run in a normal user session (it writes HKCU and creates
    shortcuts).  Some sandboxed/automation environments block those writes.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Verify = Join-Path $Root "build\verify-installer"
$Setup = Join-Path $Root "dist\EdifierR20Tray-Setup-2.0.0.exe"
$Install = Join-Path $Verify "install\EdifierR20Tray"

function Check([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok  - $Message"
}

if (-not (Test-Path $Setup)) {
    throw "Setup executable not found: $Setup (run packaging\build_windows.ps1 first)"
}

Remove-Item $Verify -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Verify | Out-Null

Write-Host "`n== 1. silent install =="
& $Setup --silent --dir $Install --no-desktop --no-autostart --no-launch
$deadline = (Get-Date).AddSeconds(120)
while (-not (Test-Path (Join-Path $Install "Uninstall.exe")) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
}
Check (Test-Path (Join-Path $Install "EdifierR20Tray.exe")) "application executable installed"
Check (Test-Path (Join-Path $Install "_internal")) "application payload installed"
Check (Test-Path (Join-Path $Install "Uninstall.exe")) "uninstaller installed"

$regInstall = (Get-ItemProperty "HKCU:\Software\EdifierR20Tray" -ErrorAction SilentlyContinue).InstallDir
Check ($regInstall -and $regInstall.ToLower() -eq $Install.ToLower()) "registry install dir written"
$uninstallString = (Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\EdifierR20Tray").UninstallString
Check ($uninstallString -like "*Uninstall.exe*") "Add/Remove Programs entry created"

Write-Host "`n== 2. packaged application runs =="
& (Join-Path $Install "EdifierR20Tray.exe") --diagnose --no-message
$report = Join-Path $env:APPDATA "EdifierR20Tray\logs\diagnose.txt"
for ($i = 0; $i -lt 60 -and -not (Test-Path $report); $i++) { Start-Sleep -Milliseconds 250 }
Check (Test-Path $report) "diagnostics report written"
$reportText = Get-Content $report -Raw
Check ($reportText -match "frozen build\s*:\s*True") "packaged (frozen) build"
Check ($reportText -match "PyQt6") "Qt runtime available"

Write-Host "`n== 3. tray application starts =="
& (Join-Path $Install "EdifierR20Tray.exe") --autostart
Start-Sleep -Seconds 10
$running = Get-Process -Name EdifierR20Tray -ErrorAction SilentlyContinue
Check ($running -ne $null) "tray application running"
Check (-not (Test-Path (Join-Path $env:APPDATA "EdifierR20Tray\logs\crash.log"))) "no crash log"
if ($running) { $running | Stop-Process -Force }
Start-Sleep -Seconds 2

Write-Host "`n== 4. silent uninstall =="
& (Join-Path $Install "Uninstall.exe") --silent
$deadline = (Get-Date).AddSeconds(120)
while ((Test-Path $Install) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
}
Check (-not (Test-Path $Install)) "install folder removed"
Check (-not (Get-ItemProperty "HKCU:\Software\EdifierR20Tray" -ErrorAction SilentlyContinue)) "install registry key removed"
Check (-not (Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\EdifierR20Tray" -ErrorAction SilentlyContinue)) "Add/Remove Programs entry removed"
Check (Test-Path (Join-Path $env:APPDATA "EdifierR20Tray")) "user settings kept by a silent uninstall"

Write-Host "`nINSTALLER VERIFICATION OK" -ForegroundColor Green
