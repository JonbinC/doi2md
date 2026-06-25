#requires -Version 5.1
$ErrorActionPreference = "Stop"

param(
  [string]$ApiKey = $env:MDTERO_API_KEY,
  [string]$Label = "",
  [string]$Version = $(if ($env:MDTERO_RELAY_VERSION) { $env:MDTERO_RELAY_VERSION } else { "0.1.0" }),
  [string]$BaseUrl = $(if ($env:MDTERO_RELAY_BASE_URL) { $env:MDTERO_RELAY_BASE_URL } else { "https://mdtero.com/releases/relay" }),
  [string]$InstallDir = $(Join-Path $env:LOCALAPPDATA "Mdtero\bin")
)

function Write-Info([string]$Message) {
  Write-Host $Message
}

$Arch = switch ((Get-CimInstance Win32_Processor).Architecture) {
  9 { "amd64" }
  12 { "arm64" }
  default { "amd64" }
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Target = Join-Path $InstallDir "mdtero-relay.exe"
$Archive = Join-Path $InstallDir "mdtero-relay-install.tgz"
$Url = "$BaseUrl/v$Version/mdtero-relay-windows-$Arch.tgz"

Write-Info "Installing mdtero-relay $Version for windows/$Arch ..."
Invoke-WebRequest -Uri $Url -OutFile $Archive
tar -xzf $Archive -C $InstallDir
Remove-Item $Archive -Force
if (-not (Test-Path $Target)) {
  Rename-Item (Join-Path $InstallDir "mdtero-relay") $Target
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir*") {
  [Environment]::SetEnvironmentVariable("Path", "$InstallDir;$userPath", "User")
  $env:Path = "$InstallDir;$env:Path"
  Write-Info "Added $InstallDir to user PATH"
}

$InstallArgs = @("install")
if ($ApiKey) { $InstallArgs += @("--api-key", $ApiKey) }
if ($Label) { $InstallArgs += @("--label", $Label) }

Write-Info "Setting up background service ..."
& $Target @InstallArgs

Write-Info ""
Write-Info "Done. Campus relay is installed."
Write-Info "Check status: mdtero-relay status"
Write-Info "Logs: $env:LOCALAPPDATA\mdtero-relay\relay.log"
