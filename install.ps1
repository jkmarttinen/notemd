# Installs notemd on Windows.
#   - Start Menu shortcut "notemd"
#   - Startup shortcut, so the app runs in the background after sign-in (global hotkey, default Win+Space)
# Run from this folder:  powershell -ExecutionPolicy Bypass -File .\install.ps1
# Options:  -Hotkey "ctrl+alt+n"   (modifiers: win, ctrl, alt, shift)     -NoAutostart
param([string]$Hotkey = "win+space", [switch]$NoAutostart)

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $runner) {
    $runner = (Get-Command pyw.exe -ErrorAction SilentlyContinue).Source   # Python launcher
}
if (-not $runner) {
    Write-Error "Python 3 was not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')."
    exit 1
}
$script = '"' + (Join-Path $dir "notemd_win.pyw") + '"'
$shell = New-Object -ComObject WScript.Shell

function New-Shortcut($path, $arguments) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $runner
    $lnk.Arguments = $arguments
    $lnk.WorkingDirectory = $dir
    $lnk.IconLocation = (Join-Path $dir "notemd.ico")
    $lnk.Description = "notemd quick notes"
    $lnk.Save()
    Write-Host "Created: $path"
}

$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\notemd.lnk"
New-Shortcut $startMenu "$script --hotkey $Hotkey"

if (-not $NoAutostart) {
    $startup = Join-Path ([Environment]::GetFolderPath("Startup")) "notemd.lnk"
    New-Shortcut $startup "$script --hidden --hotkey $Hotkey"
}

# start it right away, hidden in the background
Start-Process -FilePath $runner -ArgumentList "$script --hidden --hotkey $Hotkey"
Write-Host "notemd is running. Press $Hotkey to open it. (Ctrl+Q inside the window quits the app.)"
