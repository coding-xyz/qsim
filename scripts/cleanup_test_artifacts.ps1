param(
  [string[]]$Targets = @(".pytest_tmp*", "runs/pytest_*"),
  [switch]$ForceStopPython
)

$ErrorActionPreference = "Continue"

if ($ForceStopPython) {
  Get-Process python, python3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

foreach ($t in $Targets) {
  Get-ChildItem -Path $t -ErrorAction SilentlyContinue | ForEach-Object {
    try {
      # Remove read-only flag first, then delete.
      attrib -r $_.FullName /s /d 2>$null | Out-Null
      Remove-Item -Recurse -Force $_.FullName -ErrorAction Stop
      Write-Output "Removed: $($_.FullName)"
    } catch {
      Write-Warning "Failed to remove: $($_.FullName) :: $($_.Exception.Message)"
    }
  }
}
