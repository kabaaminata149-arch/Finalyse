# creer_raccourci_bureau.ps1
# Lance ce script une seule fois pour creer le raccourci bureau

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$BatchFile  = Join-Path $ScriptDir "Finalyse.bat"
$Desktop    = [Environment]::GetFolderPath("Desktop")
$Shortcut   = Join-Path $Desktop "Finalyse.lnk"

$WshShell   = New-Object -ComObject WScript.Shell
$Lnk        = $WshShell.CreateShortcut($Shortcut)
$Lnk.TargetPath       = $BatchFile
$Lnk.WorkingDirectory = $ScriptDir
$Lnk.WindowStyle      = 1
$Lnk.Description      = "Finalyse — Analyse Intelligente de Factures"

# Icone : utiliser pythonw.exe si pas de .ico
$IcoPath = Join-Path $ScriptDir "frontend\assets\logo.ico"
if (Test-Path $IcoPath) {
    $Lnk.IconLocation = $IcoPath
} else {
    $PythonW = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)?.Source
    if ($PythonW) { $Lnk.IconLocation = $PythonW }
}

$Lnk.Save()
Write-Host "Raccourci cree sur le bureau : $Shortcut" -ForegroundColor Green
Write-Host "Double-cliquez sur 'Finalyse' pour lancer l'application." -ForegroundColor Cyan
