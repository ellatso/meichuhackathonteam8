# SUMO 環境檢查與診斷腳本
# 檢查 SUMO 安裝、環境變數、依賴和配置

param(
    [switch]$Detailed,
    [switch]$Fix,
    [switch]$Download
)

Write-Host "=== SUMO Environment Checker ===" -ForegroundColor Green
Write-Host "Checking SUMO installation and configuration...`n"

# 結果統計
$CheckResults = @{
    Passed = 0
    Failed = 0
    Warnings = 0
    Issues = @()
    Recommendations = @()
}

function Write-Check {
    param($Message, $Status, $Details = "")
    
    $Symbol = switch ($Status) {
        "Pass" { "✓"; $CheckResults.Passed++ }
        "Fail" { "✗"; $CheckResults.Failed++; $CheckResults.Issues += $Message }
        "Warn" { "⚠"; $CheckResults.Warnings++ }
    }
    
    $Color = switch ($Status) {
        "Pass" { "Green" }
        "Fail" { "Red" }
        "Warn" { "Yellow" }
    }
    
    Write-Host "$Symbol $Message" -ForegroundColor $Color
    if ($Details -and $Detailed) {
        Write-Host "  $Details" -ForegroundColor Gray
    }
}

# 1. 檢查 SUMO_HOME 環境變數
Write-Host "1. Environment Variables" -ForegroundColor Cyan
$SUMO_HOME = $env:SUMO_HOME

if ($SUMO_HOME) {
    Write-Check "SUMO_HOME is set" "Pass" "Path: $SUMO_HOME"
    
    if (Test-Path $SUMO_HOME) {
        Write-Check "SUMO_HOME directory exists" "Pass"
    } else {
        Write-Check "SUMO_HOME directory does not exist" "Fail"
        $CheckResults.Recommendations += "Update SUMO_HOME to point to valid SUMO installation"
    }
} else {
    Write-Check "SUMO_HOME environment variable not set" "Fail"
    $CheckResults.Recommendations += "Set SUMO_HOME environment variable"
}

# 2. 檢查 SUMO 執行檔
Write-Host "`n2. SUMO Executables" -ForegroundColor Cyan

$SumoExecutables = @("sumo", "sumo-gui", "netconvert", "duarouter", "traci")
$SumoFound = $false

foreach ($exe in $SumoExecutables) {
    try {
        $ExePath = Get-Command "$exe.exe" -ErrorAction SilentlyContinue
        if ($ExePath) {
            Write-Check "$exe.exe found in PATH" "Pass" $ExePath.Source
            $SumoFound = $true
            
            # 獲取版本資訊
            if ($exe -eq "sumo" -and $Detailed) {
                try {
                    $Version = & sumo.exe --version 2>&1 | Select-Object -First 1
                    Write-Host "    Version: $Version" -ForegroundColor Gray
                } catch {
                    Write-Host "    Version check failed" -ForegroundColor Gray
                }
            }
        } else {
            Write-Check "$exe.exe not found in PATH" "Warn"
        }
    } catch {
        Write-Check "Error checking $exe.exe" "Fail" $_.Exception.Message
    }
}

# 檢查 SUMO_HOME/bin 目錄
if ($SUMO_HOME -and (Test-Path $SUMO_HOME)) {
    $SumoBinDir = Join-Path $SUMO_HOME "bin"
    if (Test-Path $SumoBinDir) {
        Write-Check "SUMO bin directory exists" "Pass" $SumoBinDir
        
        foreach ($exe in $SumoExecutables) {
            $ExePath = Join-Path $SumoBinDir "$exe.exe"
            if (Test-Path $ExePath) {
                Write-Check "$exe.exe found in SUMO bin" "Pass"
            } else {
                Write-Check "$exe.exe missing from SUMO bin" "Warn"
            }
        }
    } else {
        Write-Check "SUMO bin directory not found" "Fail"
    }
}

# 3. 檢查 Python SUMO 模組
Write-Host "`n3. Python SUMO Libraries" -ForegroundColor Cyan

$PythonModules = @("sumolib", "traci")
foreach ($module in $PythonModules) {
    try {
        $ImportTest = python -c "import $module; print('$module import successful')" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Check "Python $module module available" "Pass"
            
            if ($Detailed) {
                $ModuleInfo = python -c "import $module; print(f'Version: {getattr($module, '__version__', 'Unknown')}'); print(f'Path: {$module.__file__}')" 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "    $ModuleInfo" -ForegroundColor Gray
                }
            }
        } else {
            Write-Check "Python $module module not available" "Fail" $ImportTest
            $CheckResults.Recommendations += "Install SUMO Python libraries: pip install sumolib traci"
        }
    } catch {
        Write-Check "Error checking Python $module" "Fail" $_.Exception.Message
    }
}

# 4. 檢查系統 PATH
Write-Host "`n4. System PATH Analysis" -ForegroundColor Cyan

$SystemPath = $env:PATH -split ";"
$SumoInPath = $false

foreach ($pathEntry in $SystemPath) {
    if ($pathEntry -like "*sumo*") {
        Write-Check "SUMO-related PATH entry found" "Pass" $pathEntry
        $SumoInPath = $true
    }
}

if (-not $SumoInPath) {
    Write-Check "No SUMO entries found in PATH" "Warn"
    if ($SUMO_HOME) {
        $CheckResults.Recommendations += "Add $SUMO_HOME\bin to system PATH"
    }
}

# 5. 測試 SUMO 功能
Write-Host "`n5. SUMO Functionality Test" -ForegroundColor Cyan

if ($SumoFound) {
    try {
        # 測試基本命令
        $HelpOutput = sumo.exe --help 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Check "SUMO help command works" "Pass"
        } else {
            Write-Check "SUMO help command failed" "Fail"
        }
        
        # 測試版本命令
        $VersionOutput = sumo.exe --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Check "SUMO version command works" "Pass"
            if ($Detailed) {
                Write-Host "    $($VersionOutput | Select-Object -First 3 | Out-String)" -ForegroundColor Gray
            }
        } else {
            Write-Check "SUMO version command failed" "Fail"
        }
        
    } catch {
        Write-Check "SUMO functionality test failed" "Fail" $_.Exception.Message
    }
} else {
    Write-Check "Cannot test SUMO functionality - not found" "Fail"
}

# 6. 檢查專案 SUMO 資產
Write-Host "`n6. Project SUMO Assets" -ForegroundColor Cyan

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$AssetsDir = Join-Path $ProjectRoot "backend\assets\sumo_corridor"

if (Test-Path $AssetsDir) {
    Write-Check "SUMO assets directory exists" "Pass" $AssetsDir
    
    $RequiredAssets = @(
        "corridor.net.xml",
        "corridor.rou.xml", 
        "corridor.sumocfg"
    )
    
    foreach ($asset in $RequiredAssets) {
        $AssetPath = Join-Path $AssetsDir $asset
        if (Test-Path $AssetPath) {
            Write-Check "$asset exists" "Pass"
            
            if ($Detailed -and $asset.EndsWith(".xml")) {
                # 檢查 XML 有效性
                try {
                    [xml]$XmlContent = Get-Content $AssetPath
                    Write-Check "$asset is valid XML" "Pass"
                } catch {
                    Write-Check "$asset has XML syntax errors" "Warn" $_.Exception.Message
                }
            }
        } else {
            Write-Check "$asset missing" "Fail"
            $CheckResults.Recommendations += "Create or restore $asset in $AssetsDir"
        }
    }
} else {
    Write-Check "SUMO assets directory not found" "Fail" "Expected: $AssetsDir"
    $CheckResults.Recommendations += "Create SUMO assets directory and files"
}

# 7. 檢查防火牆/權限問題
Write-Host "`n7. System Permissions" -ForegroundColor Cyan

try {
    # 檢查當前用戶權限
    $CurrentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    $IsAdmin = $CurrentPrincipal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
    
    if ($IsAdmin) {
        Write-Check "Running with administrator privileges" "Pass"
    } else {
        Write-Check "Running without administrator privileges" "Warn" "Some SUMO features may require elevated privileges"
    }
} catch {
    Write-Check "Cannot determine user privileges" "Warn"
}

# 8. 提供安裝指引
if (-not $SumoFound -or $CheckResults.Failed -gt 0) {
    Write-Host "`n8. Installation Guidance" -ForegroundColor Cyan
    
    Write-Host "SUMO Installation Instructions:" -ForegroundColor Yellow
    Write-Host "1. Download SUMO from: https://eclipse.dev/sumo/" -ForegroundColor White
    Write-Host "2. Choose 'Windows x64 installer' for Windows systems" -ForegroundColor White
    Write-Host "3. During installation, check 'Add SUMO to PATH'" -ForegroundColor White
    Write-Host "4. Set SUMO_HOME environment variable to installation directory" -ForegroundColor White
    Write-Host "5. Restart PowerShell/VSCode after installation" -ForegroundColor White
    Write-Host ""
    Write-Host "Alternative: Using Conda/Mamba:" -ForegroundColor Yellow
    Write-Host "  conda install -c conda-forge sumo" -ForegroundColor White
    Write-Host ""
    Write-Host "Python Libraries:" -ForegroundColor Yellow
    Write-Host "  pip install sumolib traci" -ForegroundColor White
}

# 自動修復選項
if ($Fix -and $CheckResults.Failed -gt 0) {
    Write-Host "`n=== Attempting Automatic Fixes ===" -ForegroundColor Yellow
    
    # 嘗試安裝 Python 模組
    if ($CheckResults.Issues -contains "Python sumolib module not available") {
        Write-Host "Installing sumolib..."
        pip install sumolib
    }
    
    if ($CheckResults.Issues -contains "Python traci module not available") {
        Write-Host "Installing traci..."
        pip install traci
    }
    
    Write-Host "Please re-run the check after fixing environment variables and PATH"
}

# 下載選項
if ($Download) {
    Write-Host "`n=== SUMO Download ===" -ForegroundColor Yellow
    Write-Host "Opening SUMO download page..."
    Start-Process "https://eclipse.dev/sumo/"
}

# 總結報告
Write-Host "`n=== Summary Report ===" -ForegroundColor Magenta
Write-Host "Checks Passed: $($CheckResults.Passed)" -ForegroundColor Green
Write-Host "Checks Failed: $($CheckResults.Failed)" -ForegroundColor Red
Write-Host "Warnings: $($CheckResults.Warnings)" -ForegroundColor Yellow

if ($CheckResults.Failed -eq 0 -and $CheckResults.Warnings -eq 0) {
    Write-Host "`n🎉 SUMO environment is properly configured!" -ForegroundColor Green
    Write-Host "You can now run GLIDE-Lite simulations." -ForegroundColor Green
} elseif ($CheckResults.Failed -eq 0) {
    Write-Host "`n⚠️  SUMO environment has minor issues but should work." -ForegroundColor Yellow
} else {
    Write-Host "`n❌ SUMO environment has critical issues that need fixing." -ForegroundColor Red
}

# 推薦操作
if ($CheckResults.Recommendations.Count -gt 0) {
    Write-Host "`nRecommended Actions:" -ForegroundColor Cyan
    for ($i = 0; $i -lt $CheckResults.Recommendations.Count; $i++) {
        Write-Host "  $($i + 1). $($CheckResults.Recommendations[$i])" -ForegroundColor White
    }
}

# 退出碼
if ($CheckResults.Failed -gt 0) {
    exit 1
} elseif ($CheckResults.Warnings -gt 0) {
    exit 2
} else {
    exit 0
}