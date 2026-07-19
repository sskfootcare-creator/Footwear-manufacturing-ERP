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
    $exe = "$path/mongodb-portable/mongodb-win32-x86_64-windows-7.0.6/bin/mongod.exe"
    if (!(Test-Path $exe)) {
        $exe = "C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe"
    }
    & $exe --dbpath "$path/mongodb-portable/data"
} -ArgumentList $ScriptDir

# Start Backend job (listening on 0.0.0.0 for LAN/WiFi access)
Write-Host "[2/3] Launching backend FastAPI job (0.0.0.0:8000)..." -ForegroundColor Yellow
$BackendJob = Start-Job -ScriptBlock {
    param($path)
    Set-Location "$path/backend"
    .venv/Scripts/python.exe -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
} -ArgumentList $ScriptDir

# Start Frontend job (listening on 0.0.0.0 for LAN/WiFi access)
Write-Host "[3/3] Launching frontend React job (0.0.0.0:3000)..." -ForegroundColor Yellow
$FrontendJob = Start-Job -ScriptBlock {
    param($path)
    $env:HOST = "0.0.0.0"
    $env:DANGEROUSLY_DISABLE_HOST_CHECK = "true"
    $env:BROWSER = "none"
    Set-Location "$path/frontend"
    cmd.exe /c npm start
} -ArgumentList $ScriptDir

# Find Local WiFi IP address for user convenience
$WiFiIP = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "*WiFi*", "*Ethernet*", "*Chandu*" -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
if (!$WiFiIP) { $WiFiIP = "192.168.x.x" }

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " SERVER READY ON LOCAL WIFI NETWORK!" -ForegroundColor Green
Write-Host " Desktop (Local):  http://localhost:3000" -ForegroundColor Cyan
Write-Host " Mobile/Tablet:    http://${WiFiIP}:3000" -ForegroundColor Yellow
Write-Host " (Open the Mobile link on your phone connected to WiFi)" -ForegroundColor Gray
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
