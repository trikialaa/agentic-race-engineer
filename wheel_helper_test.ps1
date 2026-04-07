 = Start-Process -FilePath  native\\wheel-helper\\bin\\WheelHelper.exe -NoNewWindow -RedirectStandardOutput wheel_helper_stdout.log -RedirectStandardError wheel_helper_stderr.log -PassThru
Start-Sleep -Milliseconds 2000
if (-not .HasExited) { .Kill() }
Get-Content wheel_helper_stdout.log
Get-Content wheel_helper_stderr.log
Remove-Item wheel_helper_stdout.log,wheel_helper_stderr.log
