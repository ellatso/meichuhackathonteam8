# GLIDE-Lite 幹道綠波系統

一個可演示的智慧交通信號控制系統，整合綠波控制與公車不群聚 TSP (Transit Signal Priority) 功能。

## 🎯 專案特色

- **三模式對比**：固定時制 vs GLIDE 綠波 vs GLIDE + TSP
- **即時動畫**：車輛移動、信號變化、TSP 事件視覺化
- **效能指標**：進帶率、停等次數、頭距標準差等 KPI
- **Web 介面**：React + Canvas 動畫，支援一鍵 Demo
- **模擬後端**：SUMO 交通模擬 + FastAPI REST API

## 📁 專案結構

```
GLIDE-Lite/
├── backend/                    # Python 後端
│   ├── core/glide/            # 核心演算法
│   │   ├── offsets.py         # 綠波 offset 計算
│   │   ├── tsp.py            # 公車 anti-bunching TSP
│   │   └── sumo_corridor.py  # SUMO 模擬器整合
│   ├── assets/sumo_corridor/  # SUMO 路網資產
│   │   ├── corridor.net.xml   # 3 號誌路網
│   │   ├── corridor.rou.xml   # 交通需求與路線
│   │   └── corridor.sumocfg   # SUMO 配置
│   ├── app_glide.py          # FastAPI 主應用
│   └── requirements.txt      # Python 依賴
├── frontend/                  # React 前端
│   ├── index.html
│   ├── src/
│   │   ├── pages/Glide.jsx   # 主控制頁面
│   │   └── components/CorridorCanvas.jsx  # 動畫組件
│   ├── package.json          # Node.js 依賴
│   └── vite.config.js        # Vite 配置
├── scripts/                   # 啟動腳本
│   ├── start-backend.ps1     # 後端啟動 (PowerShell)
│   ├── start-frontend.ps1    # 前端啟動 (PowerShell)
│   └── sumo-check.ps1       # SUMO 環境檢查
├── tests/                     # 測試檔案
│   ├── test_offsets.py       # 綠波計算測試
│   ├── test_tsp.py          # TSP 邏輯測試
│   └── test_sumo_smoke.py   # SUMO 整合測試
└── README.md                 # 本文件
```

## 🚀 Quick Start

### 先決條件

1. **Python 3.11+** - [下載安裝](https://www.python.org/downloads/)
2. **Node.js 18+** - [下載安裝](https://nodejs.org/)
3. **SUMO 1.18+** - [下載安裝](https://eclipse.dev/sumo/)
4. **VSCode** + PowerShell - 推薦開發環境

### 安裝 SUMO

#### Windows 安裝方式

**方法一：官方安裝器 (推薦)**
1. 前往 [SUMO 官網](https://eclipse.dev/sumo/)
2. 下載 "Windows x64 installer"
3. 安裝時勾選 "Add SUMO to PATH"
4. 設定環境變數 `SUMO_HOME` 指向安裝目錄

**方法二：Conda 安裝**
```powershell
conda install -c conda-forge sumo
```

**驗證安裝**
```powershell
# 執行 SUMO 環境檢查
.\scripts\sumo-check.ps1
```

### 一鍵啟動

**1. 啟動後端**
```powershell
# 在 VSCode PowerShell 中執行
.\scripts\start-backend.ps1

# 或指定參數
.\scripts\start-backend.ps1 -Port 8001 -Clean
```

**2. 啟動前端 (新開 PowerShell 視窗)**
```powershell
.\scripts\start-frontend.ps1

# 或指定 API URL
.\scripts\start-frontend.ps1 -ApiUrl "http://127.0.0.1:8001"
```

**3. 開始 Demo**
1. 瀏覽器打開 `http://localhost:5173`
2. 檢查 API 連線狀態 (右上角綠燈)
3. 點擊 "🎬 Demo 劇本 (三模式)" 按鈕
4. 觀看 Fixed → GLIDE → GLIDE+TSP 自動演示

## 🎭 Demo 劇本 (3 分鐘演示)

### 第一幕：Fixed 固定時制 (傳統)
- **現象**：車隊「走走停停」，頻繁紅燈等待
- **KPI**：進帶率 30-40%，較多停等

### 第二幕：GLIDE 綠波
- **現象**：綠帶對齊，車隊「一路綠燈」
- **KPI**：進帶率提升至 60-70%，旅行時間↓

### 第三幕：GLIDE + TSP (完整版)
- **現象**：
  - 頭距過大時顯示 "TSP_EXTEND +6s" 綠燈延長
  - 頭距過小時顯示 "BUS_HOLD 15s" 站點保留
- **KPI**：頭距標準差↓，公車準點率↑

## 🔧 手動操作指南

### 參數調整
- **週期 (Cycle)**：30-180 秒，預設 90 秒
- **目標速度**：20-80 km/h，預設 40 km/h  
- **模擬步數**：60-1800 步，預設 180 步 (3 分鐘)

### 單獨模式測試
1. 調整參數後點擊 "計算 Offsets"
2. 選擇單一模式：固定時制 / GLIDE 綠波 / GLIDE + TSP
3. 使用播放控制：▶ 播放、⏸ 暫停、⏹ 重置
4. 拖曳進度條查看特定時刻

### KPI 指標說明
- **進帶率**：車輛遇到綠燈的比例 (越高越好)
- **平均停等**：主線車輛平均停車次數 (越低越好)  
- **頭距標準差**：公車班距變異程度 (越低越穩定)
- **TSP 授予**：延綠事件次數
- **公車保留**：站點保留事件次數

## 🏗️ 開發指南

### 後端開發

**核心模組位置**
```
backend/core/glide/
├── offsets.py      # 綠波演算法
├── tsp.py         # TSP 控制邏輯  
└── sumo_corridor.py # SUMO 整合
```

**API 端點**
- `GET /health` - 健康檢查
- `POST /glide/plan` - 計算 offset 與綠帶
- `POST /glide/sim` - 執行模擬
- `GET /glide/modes` - 取得可用模式

**開發模式啟動**
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app_glide:app --reload --port 8001
```

### 前端開發

**主要組件**
- `pages/Glide.jsx` - 主控制介面
- `components/CorridorCanvas.jsx` - Canvas 動畫

**開發模式啟動**
```powershell
cd frontend
npm run dev
```

**環境變數設定**
```bash
# .env.local
VITE_API_URL=http://127.0.0.1:8001
VITE_DEBUG=true
```

### 測試執行

**運行所有測試**
```powershell
cd backend
python -m pytest tests/ -v
```

**單獨測試模組**
```powershell
python -m pytest tests/test_offsets.py -v
python -m pytest tests/test_tsp.py -v  
python -m pytest tests/test_sumo_smoke.py -v
```

## 🐛 故障排除 (Troubleshooting)

### 後端問題

**1. SUMO 找不到**
```
錯誤：SUMO/TraCI not available
解決：
1. 檢查 SUMO_HOME 環境變數
2. 執行 .\scripts\sumo-check.ps1 診斷
3. 重新安裝 SUMO 並重啟 PowerShell
```

**2. TraCI 連線失敗**
```
錯誤：TraCI connection failed  
解決：
1. 確認 corridor.sumocfg 檔案存在
2. 檢查 SUMO 執行權限
3. 關閉防火牆/防毒軟體暫時測試
```

**3. Python 模組導入錯誤**
```
錯誤：Cannot import core.glide modules
解決：
cd backend
pip install -r requirements.txt
# 或重新建立虛擬環境
.\scripts\start-backend.ps1 -Clean
```

**4. 端口被佔用**
```
錯誤：Port 8001 already in use
解決：
1. 更換端口：.\scripts\start-backend.ps1 -Port 8002
2. 或關閉佔用程序：Get-Process -Name *uvicorn* | Stop-Process
```

### 前端問題

**1. API 連線失敗**
```
錯誤：API 連線異常 (紅燈)
解決：
1. 確認後端已啟動 (http://127.0.0.1:8001/health)
2. 檢查 .env.local 中的 VITE_API_URL
3. 檢查防火牆設定
```

**2. Node.js 依賴問題**
```
錯誤：npm install failed
解決：
.\scripts\start-frontend.ps1 -Clean
# 或手動清理
rm -rf node_modules package-lock.json
npm install --legacy-peer-deps
```

**3. Canvas 動畫問題**
```
錯誤：車輛不動/畫面空白
解決：
1. 檢查瀏覽器開發者工具 Console
2. 確認模擬數據格式正確
3. 嘗試重新整理頁面
```

**4. Vite 啟動失敗**
```
錯誤：Vite server failed to start
解決：
1. 檢查 Node.js 版本 (需要 18+)
2. 清除 .vite 快取：rm -rf .vite
3. 更新 package.json 中的 vite 版本
```

### SUMO 相關問題

**1. projParameter 錯誤**
```
錯誤：XML parsing error with projParameter
解決：編輯 corridor.net.xml，移除 <location> 中的 projParameter="" 屬性
```

**2. 路網檔案損毀**
```
錯誤：Invalid network file
解決：重新生成 SUMO 資產或從備份恢復
```

**3. 記憶體不足**
```
錯誤：SUMO out of memory
解決：
1. 減少模擬步數 (< 300)
2. 降低車流量設定
3. 增加系統記憶體
```

### 效能最佳化

**後端效能**
- 限制模擬步數在 300 步以內
- 使用 seed 參數確保結果可重現
- 定期清理 TraCI 連線

**前端效能**
- Canvas 動畫控制在 1 Hz 更新頻率
- 車輛數量超過 50 時啟用 LOD
- 使用 Web Worker 處理大量數據

## 📊 技術架構

### 演算法核心

**GLIDE 綠波計算**
```python
offset_i = (cumulative_travel_time) mod cycle
travel_time = distance / target_speed
```

**Anti-Bunching TSP**
```python
if headway > target + tolerance:
    → 延綠/提前綠 (max 10s)
elif headway < target - tolerance:  
    → 站點保留 (10-20s)
```

**KPI 計算**
- 進帶率：green_encounters / total_encounters
- 停等次數：stop_events / vehicle_count
- 頭距標準差：std(headway_samples)

### 系統架構

```
Frontend (React + Canvas)
    ↕ HTTP/REST API
Backend (FastAPI + Python)
    ↕ TraCI Protocol  
SUMO Simulator (C++)
```

## 🛠️ 擴展開發

### 新增模式
1. 在 `tsp.py` 實現新演算法
2. 修改 `sumo_corridor.py` 的模式判斷
3. 更新前端 `SIMULATION_MODES` 陣列

### 新增 KPI  
1. 在 `calculate_kpis()` 方法添加計算邏輯
2. 更新前端 KPI 卡片顯示

### 新增路網
1. 使用 NETEDIT 或 NETCONVERT 生成新路網
2. 更新 `assets/sumo_corridor/` 下的檔案
3. 調整前端座標映射範圍

## 📝 授權與致謝

- **SUMO**: Eclipse Public License 2.0
- **專案程式碼**: MIT License  
- **React/FastAPI**: 各自 MIT License

### 參考文獻
- SUMO Documentation: https://sumo.dlr.de/docs/
- Traffic Signal Control: Koonce et al. (2008)
- Green Wave Theory: Webster (1958)

---

## 🎉 完成檢查清單

安裝完成後請確認：

- [ ] `.\scripts\sumo-check.ps1` 全部綠勾
- [ ] `http://127.0.0.1:8001/health` 回傳 healthy
- [ ] `http://localhost:5173` 顯示主介面
- [ ] API 連線狀態為綠燈
- [ ] Demo 劇本可正常播放
- [ ] 三種模式的 KPI 有明顯差異
- [ ] Canvas 動畫車輛移動流暢
- [ ] TSP 事件正確顯示

**如果有任何問題，請檢查 Troubleshooting 章節或執行診斷腳本。**

祝您使用愉快！ 🚦✨
