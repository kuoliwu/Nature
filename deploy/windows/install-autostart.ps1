<#
  驗屋預約系統：Windows 登入時自動在 WSL 背景啟動後端（不會出現視窗）

  用法（一般 PowerShell 即可，不需要系統管理員）：
    powershell -ExecutionPolicy Bypass -File \\wsl.localhost\Ubuntu-24.04\home\b9211\stock\nature\nature\deploy\windows\install-autostart.ps1

  立即啟動：  Start-ScheduledTask -TaskName InspectionServer
  查看狀態：  Get-ScheduledTask -TaskName InspectionServer | Get-ScheduledTaskInfo
  移除：      uninstall-autostart.ps1
#>
param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$LinuxUser = "b9211",
    [string]$Script = "/home/b9211/stock/nature/nature/backend/scripts/start_server.sh",
    [string]$TaskName = "InspectionServer"
)

$ErrorActionPreference = "Stop"

# 隱藏視窗的 PowerShell 啟動 wsl.exe；wsl.exe 會一直執行，WSL 因此不會自動關閉
$command = "wsl.exe -d $Distro -u $LinuxUser -- bash $Script"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"$command`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "驗屋預約系統後端（WSL）" -Force | Out-Null

Write-Host "已建立排程工作「$TaskName」：之後登入 Windows 會自動啟動後端。"
Write-Host "現在立即啟動：Start-ScheduledTask -TaskName $TaskName"
Write-Host "日誌：\\wsl.localhost\$Distro$($Script -replace '/scripts/start_server.sh','/logs/server.log' -replace '/','\')"
