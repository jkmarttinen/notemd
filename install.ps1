# Installs notemd on Windows: creates a Start Menu shortcut with the hotkey Ctrl+Alt+N.
# Run from this folder:  powershell -ExecutionPolicy Bypass -File .\install.ps1
# Optional: change the hotkey, e.g.  -Hotkey "CTRL+ALT+M"
param([string]$Hotkey = "CTRL+ALT+N")

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
$args_ = '"' + (Join-Path $dir "notemd_win.pyw") + '"'
if (-not $runner) {
    $runner = (Get-Command pyw.exe -ErrorAction SilentlyContinue).Source   # Python launcher
}
if (-not $runner) {
    Write-Error "Python 3 was not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')."
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$lnkPath = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\notemd.lnk"
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = $runner
$lnk.Arguments = $args_
$lnk.WorkingDirectory = $dir
$lnk.IconLocation = (Join-Path $dir "notemd.ico")
$lnk.Description = "notemd quick notes"
$lnk.Hotkey = $Hotkey
$lnk.Save()
Write-Host "Installed: $lnkPath"
Write-Host "Hotkey: $Hotkey (it may take a moment, or a sign-out, before Windows picks it up)"
