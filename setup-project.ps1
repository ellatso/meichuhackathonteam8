# GLIDE-Lite 專案一鍵設置腳本
# 在空資料夾中執行此腳本，將自動創建完整的專案結構

Write-Host "=== GLIDE-Lite 專案設置 ===" -ForegroundColor Green

# 檢查當前目錄
$CurrentDir = Get-Location
Write-Host "設置目錄: $CurrentDir" -ForegroundColor Yellow

# 創建目錄結構
Write-Host "創建目錄結構..." -ForegroundColor Cyan

$Directories = @(
    "backend\core\glide",
    "backend\assets\sumo_corridor", 
    "frontend\src\pages",
    "frontend\src\components",
    "scripts",
    "tests"
)

foreach ($dir in $Directories) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    Write-Host "✓ $dir" -ForegroundColor Green
}

# 創建空檔案（您需要手動填入內容）
Write-Host "`n創建檔案結構..." -ForegroundColor Cyan

$Files = @{
    # 後端核心
    "backend\core\glide\__init__.py" = "# GLIDE 核心模組"
    "backend\core\glide\offsets.py" = "# 綠波 Offset 計算模組"
    "backend\core\glide\tsp.py" = "# TSP 控制模組" 
    "backend\core\glide\sumo_corridor.py" = "# SUMO 模擬器整合"
    "backend\app_glide.py" = "# FastAPI 主應用"
    "backend\requirements.txt" = "# Python 依賴清單"
    
    # SUMO 資產
    "backend\assets\sumo_corridor\corridor.net.xml" = "<!-- SUMO 路網檔案 -->"
    "backend\assets\sumo_corridor\corridor.rou.xml" = "<!-- SUMO 路線檔案 -->"
    "backend\assets\sumo_corridor\corridor.sumocfg" = "<!-- SUMO 配置檔案 -->"
    
    # 前端
    "frontend\package.json" = "{}"
    "frontend\vite.config.js" = "// Vite 配置"
    "frontend\tailwind.config.js" = "// Tailwind 配置"
    "frontend\postcss.config.js" = "// PostCSS 配置"
    "frontend\index.html" = "<!DOCTYPE html>"
    "frontend\src\main.jsx" = "// React 入口"
    "frontend\src\App.jsx" = "// 主應用組件"
    "frontend\src\index.css" = "/* 全域樣式 */"
    "frontend\src\pages\Glide.jsx" = "// 主控制頁面"
    "frontend\src\components\CorridorCanvas.jsx" = "// 動畫組件"
    
    # 腳本
    "scripts\start-backend.ps1" = "# 後端啟動腳本"
    "scripts\start-frontend.ps1" = "# 前端啟動腳本"
    "scripts\sumo-check.ps1" = "# SUMO 檢查腳本"
    
    # 測試
    "tests\test_offsets.py" = "# 綠波計算測試"
    "tests\test_tsp.py" = "# TSP 邏輯測試"
    "tests\test_sumo_smoke.py" = "# SUMO 煙霧測試"
    
    # 說明文件
    "README.md" = "# GLIDE-Lite 幹道綠波系統"
    ".gitignore" = @"
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
.venv/
venv/
ENV/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Node.js
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*

# Build outputs
dist/
build/
.next/
.nuxt/
.vite/

# Environment variables
.env
.env.local
.env.development.local
.env.test.local
.env.production.local

# OS
.DS_Store
Thumbs.db

# SUMO
*.fcd.xml
*.emission.xml
*.log
tripinfo.xml
summary.xml
additional.add.xml

# Logs
logs/
*.log

# Coverage
coverage/
.nyc_output/
.coverage
htmlcov/

# Temporary files
*.tmp
*.temp
"@
}

foreach ($file in $Files.GetEnumerator()) {
    $filePath = $file.Key
    $content = $file.Value
    
    New-Item -ItemType File -Path $filePath -Force | Out-Null
    Set-Content -Path $filePath -Value $content -Encoding UTF8
    Write-Host "✓ $filePath" -ForegroundColor Green
}

Write-Host "`n📁 專案結構已創建！" -ForegroundColor Green
Write-Host "`n📋 接下來的步驟：" -ForegroundColor Yellow
Write-Host "1. 從 Claude 回應中複製各個檔案的完整內容到對應檔案" -ForegroundColor White
Write-Host "2. 安裝 SUMO: https://eclipse.dev/sumo/" -ForegroundColor White
Write-Host "3. 設定 SUMO_HOME 環境變數" -ForegroundColor White  
Write-Host "4. 執行: .\scripts\sumo-check.ps1" -ForegroundColor White
Write-Host "5. 執行: .\scripts\start-backend.ps1" -ForegroundColor White
Write-Host "6. 執行: .\scripts\start-frontend.ps1" -ForegroundColor White

Write-Host "`n📖 詳細說明請參考 README.md" -ForegroundColor Cyan

# 顯示目錄樹狀結構
Write-Host "`n📂 專案目錄結構：" -ForegroundColor Cyan
tree /F | Select-Object -First 50

Write-Host "`n🎉 設置完成！開始複製檔案內容吧！" -ForegroundColor Green