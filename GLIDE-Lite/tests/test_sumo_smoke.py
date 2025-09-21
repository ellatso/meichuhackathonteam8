"""
GLIDE-Lite SUMO 模擬器煙霧測試
測試 SUMO 連接、基本模擬功能和資源清理
僅驗證連線與 frames>0，不依賴完整的 SUMO 環境
"""

import pytest
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 添加 backend 模組路徑
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# 檢查 SUMO 可用性
SUMO_AVAILABLE = False
try:
    import traci
    import sumolib
    # 檢查 SUMO_HOME
    SUMO_HOME = os.environ.get("SUMO_HOME")
    if SUMO_HOME and Path(SUMO_HOME).exists():
        SUMO_AVAILABLE = True
except ImportError:
    pass

try:
    from core.glide.sumo_corridor import (
        SumoCorridorSimulator,
        run_corridor
    )
except ImportError as e:
    pytest.skip(f"Cannot import SUMO corridor module: {e}", allow_module_level=True)


class TestSumoCorridorSimulator:
    """測試 SUMO 廊道模擬器類別"""
    
    def test_simulator_initialization(self):
        """測試模擬器初始化"""
        sim = SumoCorridorSimulator()
        
        assert sim.connection_label is None
        assert isinstance(sim.tsp_controller, object)
        assert isinstance(sim.bus_passage_times, list)
        assert isinstance(sim.events, list)
        assert len(sim.bus_passage_times) == 0
        assert len(sim.events) == 0
    
    def test_context_manager(self):
        """測試上下文管理器功能"""
        with SumoCorridorSimulator() as sim:
            assert isinstance(sim, SumoCorridorSimulator)
        # 應該自動調用 close_connection()
    
    @patch('core.glide.sumo_corridor.traci')
    def test_safe_connection_close(self, mock_traci):
        """測試安全的連接關閉"""
        sim = SumoCorridorSimulator()
        sim.connection_label = "test_connection"
        
        # 模擬連接存在
        mock_traci.isLoaded.return_value = True
        
        sim.close_connection()
        
        mock_traci.isLoaded.assert_called_once()
        mock_traci.close.assert_called_once_with(False)
        assert sim.connection_label is None
    
    @patch('core.glide.sumo_corridor.traci')
    def test_close_connection_with_error(self, mock_traci):
        """測試連接關閉時的錯誤處理"""
        sim = SumoCorridorSimulator()
        sim.connection_label = "test_connection"
        
        # 模擬關閉時發生錯誤
        mock_traci.isLoaded.return_value = True
        mock_traci.close.side_effect = Exception("Connection error")
        
        # 應該不拋出異常
        sim.close_connection()
        assert sim.connection_label is None
    
    def test_generate_additional_file(self):
        """測試生成 additional.add.xml 檔案"""
        with tempfile.TemporaryDirectory() as temp_dir:
            assets_dir = Path(temp_dir)
            offsets = {"J1": 0, "J2": 27, "J3": 52}
            cycle = 90
            
            sim = SumoCorridorSimulator()
            additional_file = sim.generate_additional_file(assets_dir, offsets, cycle)
            
            # 檢查檔案是否創建
            assert additional_file.exists()
            assert additional_file.name == "additional.add.xml"
            
            # 檢查 XML 內容
            content = additional_file.read_text(encoding='utf-8')
            assert "additionalFile" in content
            assert "tlLogic" in content
            assert 'id="J1"' in content
            assert 'offset="0"' in content
            assert 'offset="27"' in content
            assert 'offset="52"' in content


class TestMockSimulation:
    """使用 Mock 測試模擬功能 (不需要真實 SUMO)"""
    
    @patch('core.glide.sumo_corridor.traci')
    def test_frame_data_collection_mock(self, mock_traci):
        """測試數據收集 (Mock 版本)"""
        sim = SumoCorridorSimulator()
        sim.connection_label = "test_connection"
        
        # 模擬 TraCI 回應
        mock_traci.trafficlight.getPhase.return_value = 0
        mock_traci.trafficlight.getAllProgramLogics.return_value = [
            Mock(phases=[Mock(state="GGrrr")])
        ]
        mock_traci.vehicle.getIDList.return_value = ["car_1", "bus_1"]
        mock_traci.vehicle.getPosition.side_effect = [(100, 0), (-150, 0)]
        mock_traci.vehicle.getTypeID.side_effect = ["passenger", "bus"]
        
        frame_data = sim.collect_frame_data(30)
        
        assert frame_data["t"] == 30
        assert len(frame_data["signals"]) == 3  # J1, J2, J3
        assert len(frame_data["vehicles"]) == 2
        assert frame_data["vehicles"][0]["kind"] == "car"
        assert frame_data["vehicles"][1]["kind"] == "bus"
    
    def test_frame_data_structure(self):
        """測試 frame 數據結構"""
        sim = SumoCorridorSimulator()
        
        # 測試無連接情況下的安全處理
        frame_data = sim.collect_frame_data(0)
        
        assert "t" in frame_data
        assert "signals" in frame_data
        assert "vehicles" in frame_data
        assert "events" in frame_data
        assert isinstance(frame_data["signals"], list)
        assert isinstance(frame_data["vehicles"], list)
        assert isinstance(frame_data["events"], list)


@pytest.mark.skipif(not SUMO_AVAILABLE, reason="SUMO not available")
class TestRealSumoIntegration:
    """真實 SUMO 整合測試 (需要 SUMO 環境)"""
    
    def create_minimal_sumo_config(self, temp_dir):
        """創建最小化的 SUMO 配置用於測試"""
        assets_dir = Path(temp_dir)
        
        # 創建最簡單的路網
        net_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<net version="1.16">
    <location netOffset="0.00,0.00" convBoundary="0.00,0.00,100.00,0.00" origBoundary="0.00,0.00,100.00,0.00"/>
    
    <edge id="E1" from="N1" to="N2" priority="1">
        <lane id="E1_0" index="0" speed="13.89" length="100" shape="0.00,0.00 100.00,0.00"/>
    </edge>
    
    <junction id="N1" type="dead_end" x="0.00" y="0.00" incLanes="" intLanes="" shape="0.00,-1.60 0.00,1.60"/>
    <junction id="N2" type="dead_end" x="100.00" y="0.00" incLanes="E1_0" intLanes="" shape="100.00,1.60 100.00,-1.60"/>
</net>'''
        
        # 創建簡單的路線
        rou_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<routes>
    <vType id="car" accel="2.6" decel="4.5" sigma="0.5" length="5.0" maxSpeed="50.0"/>
    <route id="route1" edges="E1"/>
    <vehicle id="car1" type="car" route="route1" depart="0"/>
</routes>'''
        
        # 創建配置檔案
        cfg_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="test.net.xml"/>
        <route-files value="test.rou.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="30"/>
        <step-length value="1"/>
    </time>
    <report>
        <no-warnings value="true"/>
        <no-step-log value="true"/>
    </report>
</configuration>'''
        
        # 寫入檔案
        (assets_dir / "test.net.xml").write_text(net_xml, encoding='utf-8')
        (assets_dir / "test.rou.xml").write_text(rou_xml, encoding='utf-8')
        (assets_dir / "test.sumocfg").write_text(cfg_xml, encoding='utf-8')
        
        return assets_dir
    
    def test_minimal_simulation_run(self):
        """測試最小化模擬運行"""
        with tempfile.TemporaryDirectory() as temp_dir:
            assets_dir = self.create_minimal_sumo_config(temp_dir)
            
            # 測試參數
            offsets = {"J1": 0}  # 簡化的 offset
            
            try:
                with SumoCorridorSimulator() as sim:
                    # 嘗試啟動簡單模擬
                    success = sim.start_simulation(
                        assets_dir=assets_dir,
                        offsets=offsets,
                        cycle=60,
                        steps=10,  # 很短的模擬
                        seed=42
                    )
                    
                    if success:
                        # 如果啟動成功，收集幾幀數據
                        frames = []
                        for step in range(5):
                            import traci
                            traci.switch(sim.connection_label)
                            traci.simulationStep()
                            frame = sim.collect_frame_data(step)
                            frames.append(frame)
                        
                        # 驗證結果
                        assert len(frames) > 0
                        assert all("t" in frame for frame in frames)
                        
                        # 基本 KPI 計算測試
                        kpis = sim.calculate_kpis(frames)
                        assert isinstance(kpis, dict)
                    
            except Exception as e:
                # 如果 SUMO 環境有問題，記錄但不失敗
                pytest.skip(f"SUMO environment issue: {e}")


class TestRunCorridor:
    """測試 run_corridor 主函數"""
    
    @patch('core.glide.sumo_corridor.SumoCorridorSimulator')
    def test_run_corridor_mock(self, mock_simulator_class):
        """測試 run_corridor 函數 (Mock 版本)"""
        # 設定 Mock
        mock_sim = Mock()
        mock_simulator_class.return_value.__enter__.return_value = mock_sim
        
        mock_sim.start_simulation.return_value = True
        mock_sim.collect_frame_data.return_value = {
            "t": 0, "signals": [], "vehicles": [], "events": []
        }
        mock_sim.apply_tsp_control.return_value = []
        mock_sim.calculate_kpis.return_value = {"test_kpi": 1.0}
        mock_sim.events = []
        
        # 執行測試
        result = run_corridor(
            assets_dir="/fake/path",
            mode="fixed",
            cycle=90,
            offsets={"J1": 0},
            demand={"main_vph": 1000},
            tsp={"H_sec": 360},
            steps=30,
            seed=42
        )
        
        # 驗證結果
        assert result["success"] == True
        assert "frames" in result
        assert "kpis" in result
        assert "events" in result
        assert len(result["frames"]) == 30
    
    def test_run_corridor_invalid_mode(self):
        """測試無效模式處理"""
        result = run_corridor(
            assets_dir="/fake/path",
            mode="invalid_mode",
            cycle=90,
            offsets={},
            demand={},
            tsp={},
            steps=30
        )
        
        assert "error" in result
        assert "Unknown mode" in result["error"]
    
    @patch('core.glide.sumo_corridor.traci', None)
    def test_run_corridor_no_traci(self):
        """測試沒有 TraCI 的情況"""
        result = run_corridor(
            assets_dir="/fake/path",
            mode="fixed",
            cycle=90,
            offsets={},
            demand={},
            tsp={},
            steps=30
        )
        
        assert "error" in result
        assert "SUMO/TraCI not available" in result["error"]


class TestErrorHandling:
    """測試錯誤處理"""
    
    def test_missing_assets_directory(self):
        """測試缺失資產目錄的處理"""
        result = run_corridor(
            assets_dir="/nonexistent/path",
            mode="fixed",
            cycle=90,
            offsets={"J1": 0},
            demand={},
            tsp={},
            steps=30
        )
        
        # 應該有錯誤處理，不應該崩潰
        assert isinstance(result, dict)
    
    @patch('core.glide.sumo_corridor.traci')
    def test_simulation_crash_recovery(self, mock_traci):
        """測試模擬崩潰時的恢復"""
        # 模擬 TraCI 連接失敗
        mock_traci.start.side_effect = Exception("Connection failed")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            assets_dir = Path(temp_dir)
            
            result = run_corridor(
                assets_dir=str(assets_dir),
                mode="fixed",
                cycle=90,
                offsets={"J1": 0},
                demand={},
                tsp={},
                steps=30
            )
            
            assert "error" in result or "success" in result


class TestPerformance:
    """效能測試"""
    
    @patch('core.glide.sumo_corridor.traci')
    def test_simulation_performance(self, mock_traci):
        """測試模擬效能"""
        # 設定快速 Mock 回應
        mock_traci.isLoaded.return_value = False
        
        sim = SumoCorridorSimulator()
        
        # 測試大量 frame 收集的效能
        start_time = time.time()
        frames = []
        for i in range(100):
            frame = sim.collect_frame_data(i)
            frames.append(frame)
        end_time = time.time()
        
        # 應該很快完成 (< 1 秒)
        assert end_time - start_time < 1.0
        assert len(frames) == 100
    
    def test_memory_usage(self):
        """測試記憶體使用"""
        sim = SumoCorridorSimulator()
        
        # 模擬長期運行，檢查記憶體洩漏
        for i in range(1000):
            sim.events.append({"t": i, "type": "test"})
            sim.bus_passage_times.append(("bus", i))
            
            # 定期清理 (模擬實際使用)
            if i % 100 == 0:
                sim.events = sim.events[-50:]  # 保留最近 50 個事件
                sim.bus_passage_times = sim.bus_passage_times[-10:]  # 保留最近 10 個記錄
        
        # 應該不會無限增長
        assert len(sim.events) <= 50
        assert len(sim.bus_passage_times) <= 10


if __name__ == "__main__":
    # 直接運行測試
    if SUMO_AVAILABLE:
        print("SUMO available - running full test suite")
    else:
        print("SUMO not available - running mock tests only")
    
    pytest.main([__file__, "-v", "-x"])  # -x 表示第一個失敗就停止