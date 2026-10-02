# Builds dist\PrintBotAgent.exe (single file, no console window).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Run($cmd) {
    & $cmd[0] $cmd[1..($cmd.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Failed: $($cmd -join ' ')" }
}

Run @("python", "-m", "pip", "install", "-q", "-r", "requirements-dev.txt")
Run @("python", "-m", "pytest", "tests", "-q")
Run @("python", "-c", "from printbot_agent.gui import make_icon; make_icon(256).save('icon.ico', sizes=[(16,16),(32,32),(48,48),(256,256)])")
Run @("python", "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole",
      "--name", "PrintBotAgent", "--icon", "icon.ico", "--hidden-import", "win32timezone", "run_agent.py")

& "$PSScriptRoot\sign.ps1"
Write-Host "Built: $PSScriptRoot\dist\PrintBotAgent.exe"
