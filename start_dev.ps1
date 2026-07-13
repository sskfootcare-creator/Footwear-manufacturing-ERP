# Start SSK Footwear Management ERP directly inside the current terminal session, showing live logs.

# Set up paths relative to script location
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (!$ScriptDir) { $ScriptDir = "." }

# Kill existing processes on ports 8000, 3000 and 27017 first to avoid conflicts
$ports = @(3000, 8000, 27017)
foreach ($port in $ports) {
    # Match both Listen and Established connections
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conns) {
        $pids = $conns.OwningProcess | Select-Object -Unique
        foreach ($proc_id in $pids) {
            if ($proc_id -gt 0) {
                Stop-Process -Id $proc_id -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
# Fallback hard kill using cmd taskkill for the port bindings
foreach ($port in $ports) {
    $nets = netstat -ano | Select-String ":$port\s"
    foreach ($net in $nets) {
        $m = [regex]::Match($net, '(\d+)\s*$')
        if ($m.Success) {
            $pid_to_kill = $m.Groups[1].Value
            if ($pid_to_kill -ne "0" -and $pid_to_kill -ne $pid) {
                taskkill /F /PID $pid_to_kill 2>$null
            }
        }
    }
}
Start-Sleep -Seconds 1

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Starting SSK Footwear ERP (Live Consolidated Logs)..." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Start MongoDB job
Write-Host "[1/3] Launching local MongoDB..." -ForegroundColor Yellow
$MongoJob = Start-Job -ScriptBlock {
    param($path)
    Set-Location "$path/mongodb-portable/mongodb-win32-x86_64-windows-7.0.6/bin"
    .\mongod.exe --dbpath "$path/mongodb-portable/data"
} -ArgumentList $ScriptDir

# Start Backend job
Write-Host "[2/3] Launching backend FastAPI job..." -ForegroundColor Yellow
$BackendJob = Start-Job -ScriptBlock {
    param($path)
    Set-Location "$path/backend"
    .venv/Scripts/python.exe -m uvicorn server:app --port 8000 --reload
} -ArgumentList $ScriptDir

# Start Frontend job
Write-Host "[3/3] Launching frontend React job..." -ForegroundColor Yellow
$FrontendJob = Start-Job -ScriptBlock {
    param($path)
    $env:BROWSER = "none"
    Set-Location "$path/frontend"
    cmd.exe /c npm start
} -ArgumentList $ScriptDir

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "Showing Live Updates from all jobs (Press Ctrl+C to stop)..." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

# Tail logs from all jobs in the current console
try {
    while ($true) {
        $mongoLogs = Receive-Job -Job $MongoJob
        foreach ($line in $mongoLogs) {
            Write-Host "[MongoDB] $line" -ForegroundColor Gray
        }
        $backendLogs = Receive-Job -Job $BackendJob
        foreach ($line in $backendLogs) {
            Write-Host "[Backend] $line" -ForegroundColor Yellow
        }
        $frontendLogs = Receive-Job -Job $FrontendJob
        foreach ($line in $frontendLogs) {
            Write-Host "[Frontend] $line" -ForegroundColor Cyan
        }
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host "`nStopping jobs and cleaning up..." -ForegroundColor Red
    Stop-Job -Job $MongoJob
    Remove-Job -Job $MongoJob
    Stop-Job -Job $BackendJob
    Remove-Job -Job $BackendJob
    Stop-Job -Job $FrontendJob
    Remove-Job -Job $FrontendJob
}
