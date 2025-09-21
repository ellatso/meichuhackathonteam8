# GLIDE-Lite 後端啟動腳本
# 適用於 Windows 10/11 + VSCode PowerShell

param(
    [switch]$Clean,
    [switch]$NoDeps,
    [int]$Port = 8001
)

Write-Host "=== GLIDE-Lite Backend Startup ===" -ForegroundColor Green

# 變更到後端目錄
$BackendDir = Join-Path $PSScriptRoot "..\backend"
if (-not (Test-Path $BackendDir)) {
    Write-Error "Backend directory not found: $BackendDir"
    exit 1
}

Set-Location $BackendDir
Write-Host "Working directory: $(Get-Location)" -ForegroundColor Yellow

# 檢查 Python
try {
    $PythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $PythonVersion" -ForegroundColor Green
} catch {
    Write-Error "Python not found. Please install Python 3.11+ and add to PATH"
    exit 1
}

# 虛擬環境處理
$VenvPath = ".venv"
if ($Clean -and (Test-Path $VenvPath)) {
    Write-Host "Cleaning existing virtual environment..." -ForegroundColor Yellow
    Remove-Item $VenvPath -Recurse -Force
}

if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment"
        exit 1
    }
}

# 啟動虛擬環境
$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
if (-not (Test-Path $ActivateScript)) {
    Write-Error "Virtual environment activation script not found: $ActivateScript"
    exit 1
}

Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& $ActivateScript
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to activate virtual environment"
    exit 1
}

# 升級 pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# 安裝依賴 (除非指定 -NoDeps)
if (-not $NoDeps) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    
    if (Test-Path "requirements.txt") {
        pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Some dependencies failed to install, continuing anyway..."
        }
    } else {
        Write-Warning "requirements.txt not found, installing minimal dependencies..."
        pip install fastapi uvicorn numpy
    }
}

# 檢查 SUMO 環境
Write-Host "`n=== SUMO Environment Check ===" -ForegroundColor Cyan

$SUMO_HOME = $env:SUMO_HOME
if ($SUMO_HOME) {
    Write-Host "✓ SUMO_HOME: $SUMO_HOME" -ForegroundColor Green
    
    $SumoExe = Join-Path $SUMO_HOME "bin\sumo.exe"
    if (Test-Path $SumoExe) {
        try {
            $SumoVersion = & $SumoExe --version 2>&1 | Select-Object -First 1
            Write-Host "✓ SUMO Version: $SumoVersion" -ForegroundColor Green
        } catch {
            Write-Warning "SUMO executable found but version check failed"
        }
    } else {
        Write-Warning "SUMO executable not found at: $SumoExe"
    }
} else {
    Write-Warning "SUMO_HOME environment variable not set"
    Write-Host "Please install SUMO from: https://eclipse.dev/sumo/" -ForegroundColor Yellow
    Write-Host "And set SUMO_HOME environment variable" -ForegroundColor Yellow
}

# 檢查 PATH 中的 SUMO
try {
    $SumoInPath = Get-Command sumo.exe -ErrorAction SilentlyContinue
    if ($SumoInPath) {
        Write-Host "✓ SUMO found in PATH: $($SumoInPath.Source)" -ForegroundColor Green
    } else {
        Write-Warning "SUMO not found in PATH"
    }
} catch {
    Write-Warning "SUMO not accessible from PATH"
}

# 檢查資產目錄
$AssetsDir = "assets\sumo_corridor"
if (Test-Path $AssetsDir) {
    Write-Host "✓ SUMO assets directory found" -ForegroundColor Green
    
    $RequiredFiles = @("corridor.net.xml", "corridor.rou.xml", "corridor.sumocfg")
    foreach ($file in $RequiredFiles) {
        $FilePath = Join-Path $AssetsDir $file
        if (Test-Path $FilePath) {
            Write-Host "✓ $file" -ForegroundColor Green
        } else {
            Write-Warning "✗ $file missing"
        }
    }
} else {
    Write-Warning "SUMO assets directory not found: $AssetsDir"
}

# 檢查核心模組
Write-Host "`n=== Core Modules Check ===" -ForegroundColor Cyan

$CoreModules = @(
    "core\glide\offsets.py",
    "core\glide\tsp.py", 
    "core\glide\sumo_corridor.py"
)

foreach ($module in $CoreModules) {
    if (Test-Path $module) {
        Write-Host "✓ $module" -ForegroundColor Green
    } else {
        Write-Warning "✗ $module missing"
    }
}

# 驗證 Python 導入
Write-Host "`n=== Python Import Check ===" -ForegroundColor Cyan

$ImportTest = @"
try:
    import fastapi
    import uvicorn
    import numpy
    print('✓ Core dependencies OK')
    
    try:
        import traci
        import sumolib
        print('✓ SUMO libraries OK')
    except ImportError as e:
        print(f'⚠ SUMO libraries not available: {e}')
    
    try:
        from core.glide.offsets import compute_offsets
        from core.glide.tsp import tsp_policy
        print('✓ GLIDE modules OK')
    except ImportError as e:
        print(f'⚠ GLIDE modules not available: {e}')
        
except ImportError as e:
    print(f'✗ Import error: {e}')
    exit(1)
"@

python -c $ImportTest

# 啟動服務器
Write-Host "`n=== Starting FastAPI Server ===" -ForegroundColor Green
Write-Host "Server will start on: http://127.0.0.1:$Port" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# 檢查端口是否被佔用
try {
    $PortCheck = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($PortCheck) {
        Write-Warning "Port $Port is already in use. Attempting to continue..."
    }
} catch {
    # 端口檢查失敗，繼續執行
}

# 啟動 Uvicorn 服務器
# 使用 reload-dir 和 exclude 來優化重載
try {
    uvicorn app_glide:app `
        --host 127.0.0.1 `
        --port $Port `
        --reload `
        --reload-dir . `
        --reload-exclude .venv `
        --reload-exclude uploads `
        --reload-exclude __pycache__ `
        --log-level info
} catch {
    Write-Error "Failed to start Uvicorn server: $_"
    
    # 提供故障排除建議
    Write-Host "`n=== Troubleshooting Tips ===" -ForegroundColor Red
    Write-Host "1. Check if port $Port is available"
    Write-Host "2. Verify all dependencies are installed: pip install -r requirements.txt"
    Write-Host "3. Check SUMO installation and environment variables"
    Write-Host "4. Verify app_glide.py exists and is valid"
    Write-Host "5. Try running with -NoDeps flag if dependency issues persist"
    
    exit 1
}

# 清理 (這段通常不會執行，因為 Uvicorn 會持續運行)
Write-Host "`nShutting down..." -ForegroundColor Yellow