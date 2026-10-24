# 移除開機自動啟動（不會停止目前正在執行的後端）
param([string]$TaskName = "InspectionServer")
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "已移除排程工作「$TaskName」"
