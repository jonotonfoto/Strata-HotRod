# Read-only sampler: every 30 s one CSV line about strata.exe and the system. Stops when strata.exe is gone or after 4 hours.
$out = Join-Path $PSScriptRoot 'memwatch.csv'
if (-not (Test-Path $out)) { 'time,ws_gb,private_gb,handles,threads,avail_mb,commit_free_gb,pagefile_mb,gpu_ded_mb,gpu_shared_mb,gpu_total_ded_mb,pagesin_s,faults_s' | Out-File $out -Encoding ascii }
$t0 = Get-Date
while (((Get-Date) - $t0).TotalHours -lt 4) {
  $p = Get-Process strata -ErrorAction SilentlyContinue
  if (-not $p) { break }
  $o = Get-CimInstance Win32_OperatingSystem
  $m = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
  $pp = Get-CimInstance Win32_PerfFormattedData_PerfProc_Process -Filter "Name='strata'"
  $pf = (Get-CimInstance Win32_PageFileUsage | Measure-Object CurrentUsage -Sum).Sum
  $g = Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Where-Object { $_.Name -like ("pid_" + $p.Id + "_*") } | Sort-Object DedicatedUsage -Descending | Select-Object -First 1
  $ga = (Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory | Measure-Object DedicatedUsage -Maximum).Maximum
  $line = '{0},{1:F2},{2:F2},{3},{4},{5},{6:F1},{7},{8:F0},{9:F0},{10:F0},{11},{12}' -f (Get-Date -Format 'HH:mm:ss'), ($p.WorkingSet64/1GB), ($p.PrivateMemorySize64/1GB), $p.HandleCount, $p.Threads.Count, $m.AvailableMBytes, ($o.FreeVirtualMemory/1MB), $pf, ($g.DedicatedUsage/1MB), ($g.SharedUsage/1MB), ($ga/1MB), $m.PagesInputPersec, $pp.PageFaultsPersec
  $line -replace ',(\d+),(\d\d)(?=,|$)', ',$1.$2' | Out-Null
  [System.Globalization.CultureInfo]::CurrentCulture = [System.Globalization.CultureInfo]::InvariantCulture
  $line = '{0},{1:F2},{2:F2},{3},{4},{5},{6:F1},{7},{8:F0},{9:F0},{10:F0},{11},{12}' -f (Get-Date -Format 'HH:mm:ss'), ($p.WorkingSet64/1GB), ($p.PrivateMemorySize64/1GB), $p.HandleCount, $p.Threads.Count, $m.AvailableMBytes, ($o.FreeVirtualMemory/1MB), $pf, ($g.DedicatedUsage/1MB), ($g.SharedUsage/1MB), ($ga/1MB), $m.PagesInputPersec, $pp.PageFaultsPersec
  $line | Out-File $out -Append -Encoding ascii
  Start-Sleep -Seconds 30
}
