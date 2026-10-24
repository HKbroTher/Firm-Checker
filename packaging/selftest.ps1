# 运行 Seek 自检并返回退出码：.\selftest.ps1 -Exe <Seek.exe 路径> -Name <数据目录名>
# Seek 是窗口程序，启动后不会阻塞终端，这里等待进程结束并设置超时
param([Parameter(Mandatory)] [string]$Exe, [Parameter(Mandatory)] [string]$Name)

$env:SEEK_DATA_DIR = Join-Path $env:RUNNER_TEMP $Name
$p = Start-Process -FilePath $Exe -ArgumentList "--self-test" -PassThru
$null = $p.Handle  # 先取句柄，否则进程结束后 ExitCode 可能为空
if (-not $p.WaitForExit(120000)) {
  $p.Kill()
  Write-Host "self-test timed out: $Exe"
  exit 124
}
$log = Join-Path $env:SEEK_DATA_DIR "seek.log"
if (Test-Path $log) { Get-Content $log -Tail 8 | Write-Host }
exit $p.ExitCode
