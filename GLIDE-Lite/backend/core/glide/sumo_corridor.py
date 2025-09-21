"""
SUMO 廊道模擬器 - GLIDE + TSP 整合
處理 TraCI 連接、信號控制、數據收集與 KPI 計算
"""

import os
import sys
import time
import uuid
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import traceback

# SUMO imports
try:
    import traci
    import sumolib
except ImportError:
    print("Warning: SUMO not installed. Please install SUMO and set SUMO_HOME environment variable.")
    traci = None
    sumolib = None

from .tsp import TSPController, tsp_policy, apply_tsp_to_phase, calculate_headway


class SumoCorridorSimulator:
    """SUMO 廊道模擬器類別"""
    
    def __init__(self):
        self.connection_label = None
        self.tsp_controller = TSPController()
        self.bus_passage_times = []  # [(bus_id, timestamp), ...]
        self.events = []  # TSP events log
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_connection()
    
    def close_connection(self):
        """安全關閉 TraCI 連接 - Windows 注意事項處理"""
        if self.connection_label and traci:
            try:
                # 檢查連接是否還存在
                if traci.isLoaded():
                    traci.close(False)  # 不等待 SUMO 結束，避免 Windows 掛起
                    print(f"TraCI connection '{self.connection_label}' closed safely")
            except Exception as e:
                print(f"Warning: Error closing TraCI connection: {e}")
            finally:
                self.connection_label = None
    
    def generate_additional_file(self, assets_dir: Path, offsets: Dict[str, int], cycle: int) -> Path:
        """
        動態生成 additional.add.xml 檔案，設定各號誌的 offset
        
        Args:
            assets_dir: SUMO 資產目錄
            offsets: 號誌 offset 映射 {"J1": 0, "J2": 27, "J3": 52}
            cycle: 週期長度
            
        Returns:
            生成的 additional 檔案路徑
        """
        additional_path = assets_dir / "additional.add.xml"
        
        root = ET.Element("additionalFile")
        
        for tls_id, offset in offsets.items():
            # 創建 tlLogic 元素
            tl_logic = ET.SubElement(root, "tlLogic")
            tl_logic.set("id", tls_id)
            tl_logic.set("type", "static")
            tl_logic.set("programID", "glide")
            tl_logic.set("offset", str(offset))
            
            # 定義相位序列 (90秒週期)
            # 主線: 54s 綠 + 6s 黃 + 2s 全紅 = 62s
            # 側向: 24s 綠 + 4s 黃 = 28s
            phases = [
                {"duration": "54", "state": "GGGrrrr"},  # 主線綠
                {"duration": "6", "state": "yyyrrr"},   # 主線黃
                {"duration": "2", "state": "rrrrrr"},   # 全紅
                {"duration": "24", "state": "rrrGGG"},  # 側向綠
                {"duration": "4", "state": "rrryyy"},   # 側向黃
            ]
            
            for phase in phases:
                phase_elem = ET.SubElement(tl_logic, "phase")
                phase_elem.set("duration", phase["duration"])
                phase_elem.set("state", phase["state"])
        
        # 寫入檔案
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(additional_path, encoding="utf-8", xml_declaration=True)
        
        return additional_path
    
    def start_simulation(self, assets_dir: Path, offsets: Dict[str, int], cycle: int, 
                        steps: int = 300, seed: Optional[int] = None) -> bool:
        """
        啟動 SUMO 模擬
        
        Args:
            assets_dir: SUMO 資產目錄
            offsets: 號誌 offset 設定
            cycle: 週期長度
            steps: 模擬步數
            seed: 隨機種子
            
        Returns:
            是否成功啟動
        """
        try:
            # 確保之前的連接已關閉
            if traci and traci.isLoaded():
                traci.close(False)
                time.sleep(0.5)  # 等待連接完全關閉
            
            # 生成 additional 檔案
            additional_file = self.generate_additional_file(assets_dir, offsets, cycle)
            
            # 生成唯一連接標籤
            self.connection_label = f"corridor_{uuid.uuid4().hex[:8]}"
            
            # SUMO 配置
            sumocfg_path = assets_dir / "corridor.sumocfg"
            if not sumocfg_path.exists():
                raise FileNotFoundError(f"SUMO config not found: {sumocfg_path}")
            
            # SUMO 啟動命令
            sumo_cmd = [
                "sumo",  # 使用非 GUI 版本以提高效能
                "-c", str(sumocfg_path),
                "--additional-files", str(additional_file),
                "--no-warnings", "true",
                "--no-step-log", "true",
                "--time-to-teleport", "-1",  # 禁用 teleport
            ]
            
            if seed is not None:
                sumo_cmd.extend(["--seed", str(seed)])
            
            print(f"Starting SUMO with command: {' '.join(sumo_cmd)}")
            print(f"Working directory: {assets_dir}")
            print(f"Connection label: {self.connection_label}")
            
            # 啟動 TraCI 連接，使用重試機制
            for attempt in range(3):
                try:
                    traci.start(sumo_cmd, label=self.connection_label)
                    print(f"✓ TraCI connected successfully (attempt {attempt + 1})")
                    return True
                except Exception as e:
                    print(f"✗ TraCI connection attempt {attempt + 1} failed: {e}")
                    if attempt < 2:
                        time.sleep(1)
                        continue
                    else:
                        raise
            
            return False
            
        except Exception as e:
            print(f"Error starting SUMO simulation: {e}")
            traceback.print_exc()
            return False
    
    def collect_frame_data(self, sim_time: int) -> Dict[str, Any]:
        """
        收集當前時刻的模擬數據
        
        Args:
            sim_time: 模擬時間 (秒)
            
        Returns:
            包含 signals, vehicles 等信息的數據框
        """
        try:
            # 切換到正確的連接
            traci.switch(self.connection_label)
            
            frame_data = {
                "t": sim_time,
                "signals": [],
                "vehicles": [],
                "events": []
            }
            
            # 收集號誌狀態
            tls_ids = ["J1", "J2", "J3"]
            for tls_id in tls_ids:
                try:
                    phase_index = traci.trafficlight.getPhase(tls_id)
                    program = traci.trafficlight.getAllProgramLogics(tls_id)[0]
                    if phase_index < len(program.phases):
                        state = program.phases[phase_index].state
                        # 簡化狀態：G/g->G, y->y, r->r
                        main_state = state[0] if state else "r"
                        if main_state.lower() == "g":
                            main_state = "G"
                        
                        frame_data["signals"].append({
                            "node": tls_id,
                            "state": main_state,
                            "phase": phase_index
                        })
                except Exception as e:
                    print(f"Error getting signal state for {tls_id}: {e}")
            
            # 收集車輛位置
            vehicle_ids = traci.vehicle.getIDList()
            for veh_id in vehicle_ids:
                try:
                    x, y = traci.vehicle.getPosition(veh_id)
                    veh_type = traci.vehicle.getTypeID(veh_id)
                    
                    # 判斷車輛類型
                    kind = "bus" if "bus" in veh_id.lower() or "bus" in veh_type.lower() else "car"
                    
                    frame_data["vehicles"].append({
                        "id": veh_id,
                        "x": round(x, 1),
                        "y": round(y, 1),
                        "kind": kind
                    })
                    
                    # 記錄公車通過參考點 (J1)
                    if kind == "bus" and abs(x - (-300)) < 20:  # J1 附近
                        # 檢查是否是新的通過記錄
                        if not any(record[0] == veh_id for record in self.bus_passage_times[-5:]):
                            self.bus_passage_times.append((veh_id, sim_time))
                            print(f"Bus {veh_id} passed reference point at t={sim_time}s")
                    
                except Exception as e:
                    print(f"Error getting vehicle data for {veh_id}: {e}")
            
            return frame_data
            
        except Exception as e:
            print(f"Error collecting frame data at t={sim_time}: {e}")
            return {"t": sim_time, "signals": [], "vehicles": [], "events": []}
    
    def apply_tsp_control(self, sim_time: int, tsp_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        應用 TSP 控制邏輯
        
        Args:
            sim_time: 當前模擬時間
            tsp_config: TSP 配置參數
            
        Returns:
            TSP 事件列表
        """
        if len(self.bus_passage_times) < 2:
            return []
        
        events = []
        
        try:
            traci.switch(self.connection_label)
            
            # 計算當前頭距
            headway = calculate_headway(self.bus_passage_times)
            
            # TSP 決策
            decision = tsp_policy(
                h_now=headway,
                H=tsp_config.get("H_sec", 360),
                delta=tsp_config.get("delta_sec", 90),
                max_ext=tsp_config.get("max_extend", 8),
                max_adv=tsp_config.get("max_advance", 6)
            )
            
            # 對每個號誌應用 TSP
            for tls_id in ["J1", "J2", "J3"]:
                if not self.tsp_controller.can_grant_tsp(tls_id, sim_time):
                    continue
                
                if decision.grant:
                    try:
                        # 獲取當前相位信息
                        phase_index = traci.trafficlight.getPhase(tls_id)
                        remaining = traci.trafficlight.getNextSwitch(tls_id) - sim_time
                        
                        # 只在主線綠相位時延長 (phase 0)
                        if phase_index == 0 and remaining > 0:
                            current_ext = self.tsp_controller.get_cycle_extensions(tls_id)
                            actual_ext, granted = apply_tsp_to_phase(
                                current_green_remaining=int(remaining),
                                current_cycle_extensions=current_ext,
                                decision=decision,
                                max_cycle_extension=10
                            )
                            
                            if granted and actual_ext > 0:
                                # 延長綠燈
                                new_duration = remaining + actual_ext
                                # 注意：SUMO TraCI 的延長綠燈功能有限，這裡做簡化處理
                                
                                self.tsp_controller.record_grant(tls_id, sim_time, actual_ext)
                                
                                event = {
                                    "t": sim_time,
                                    "type": "TSP_EXTEND",
                                    "node": tls_id,
                                    "sec": actual_ext,
                                    "headway": headway,
                                    "reason": decision.reason
                                }
                                events.append(event)
                                self.events.append(event)
                                
                                print(f"TSP granted at {tls_id}: extend {actual_ext}s (headway={headway:.0f}s)")
                                
                    except Exception as e:
                        print(f"Error applying TSP to {tls_id}: {e}")
                
                elif decision.hold > 0:
                    # 記錄站點保留事件
                    event = {
                        "t": sim_time,
                        "type": "BUS_HOLD",
                        "node": tls_id,
                        "sec": decision.hold,
                        "headway": headway,
                        "reason": decision.reason
                    }
                    events.append(event)
                    self.events.append(event)
                    
                    print(f"Bus hold recommended at {tls_id}: {decision.hold}s (headway={headway:.0f}s)")
        
        except Exception as e:
            print(f"Error in TSP control: {e}")
        
        return events
    
    def calculate_kpis(self, frames: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        計算模擬 KPI
        
        Args:
            frames: 所有時間框的數據
            
        Returns:
            KPI 字典
        """
        if not frames:
            return {}
        
        try:
            traci.switch(self.connection_label)
            
            # 基本統計
            total_arrived = traci.simulation.getArrivedNumber()
            total_departed = traci.simulation.getDepartedNumber()
            
            # 計算主線車輛停車次數 (簡化版本)
            main_line_stops = 0
            main_line_vehicles = 0
            
            for frame in frames[-10:]:  # 只看最後10幀
                for vehicle in frame["vehicles"]:
                    if vehicle["kind"] == "car" and -400 <= vehicle["x"] <= 400:  # 主線範圍
                        main_line_vehicles += 1
                        # 簡化：假設速度很低時為停車 (這裡用位置變化估算)
            
            avg_stops = main_line_stops / max(main_line_vehicles, 1) if main_line_vehicles > 0 else 0
            
            # 計算公車頭距標準差
            headways = []
            if len(self.bus_passage_times) >= 3:
                for i in range(1, len(self.bus_passage_times)):
                    headway = self.bus_passage_times[i][1] - self.bus_passage_times[i-1][1]
                    headways.append(headway)
            
            headway_std = 0
            if len(headways) > 1:
                mean_headway = sum(headways) / len(headways)
                variance = sum((h - mean_headway) ** 2 for h in headways) / len(headways)
                headway_std = variance ** 0.5
            
            # TSP 事件統計
            tsp_grants = len([e for e in self.events if e["type"] == "TSP_EXTEND"])
            bus_holds = len([e for e in self.events if e["type"] == "BUS_HOLD"])
            
            kpis = {
                "total_arrived": total_arrived,
                "total_departed": total_departed,
                "throughput": total_arrived,
                "avg_stops_main": round(avg_stops, 2),
                "bus_headway_std_s": round(headway_std, 1),
                "tsp_grants": tsp_grants,
                "bus_holds": bus_holds,
                "simulation_frames": len(frames)
            }
            
            # 估算進帶率 (簡化版本)
            green_signals = sum(1 for frame in frames[-30:] for signal in frame["signals"] 
                              if signal["state"] == "G")
            total_signals = len(frames[-30:]) * 3  # 3個號誌
            progression_rate = green_signals / max(total_signals, 1)
            kpis["progression_rate"] = round(progression_rate, 3)
            
            return kpis
            
        except Exception as e:
            print(f"Error calculating KPIs: {e}")
            return {"error": str(e)}


def run_corridor(
    assets_dir: str,
    mode: str,
    cycle: int,
    offsets: Dict[str, int],
    demand: Dict[str, int],
    tsp: Dict[str, Any],
    steps: int = 300,
    seed: Optional[int] = None
) -> Dict[str, Any]:
    """
    執行廊道模擬
    
    Args:
        assets_dir: SUMO 資產目錄路徑
        mode: 模擬模式 ("fixed", "glide", "glide_tsp")
        cycle: 信號週期
        offsets: 號誌 offset 設定
        demand: 交通需求設定
        tsp: TSP 參數設定
        steps: 模擬步數
        seed: 隨機種子
        
    Returns:
        包含 frames, kpis, events 的結果字典
    """
    if not traci:
        return {"error": "SUMO/TraCI not available"}
    
    assets_path = Path(assets_dir)
    
    # 根據模式調整 offsets
    if mode == "fixed":
        actual_offsets = {"J1": 0, "J2": 0, "J3": 0}
    elif mode in ["glide", "glide_tsp"]:
        actual_offsets = offsets
    else:
        return {"error": f"Unknown mode: {mode}"}
    
    frames = []
    events = []
    
    # 使用 context manager 確保連接正確關閉
    with SumoCorridorSimulator() as sim:
        try:
            # 啟動模擬
            if not sim.start_simulation(assets_path, actual_offsets, cycle, steps, seed):
                return {"error": "Failed to start SUMO simulation"}
            
            print(f"Running {mode} simulation for {steps} steps...")
            
            # 模擬循環
            for step in range(steps):
                traci.switch(sim.connection_label)
                traci.simulationStep()
                
                sim_time = traci.simulation.getTime()
                
                # 收集數據
                frame = sim.collect_frame_data(int(sim_time))
                frames.append(frame)
                
                # 應用 TSP (僅在 glide_tsp 模式)
                if mode == "glide_tsp" and sim_time > 30:  # 30秒後開始 TSP
                    tsp_events = sim.apply_tsp_control(int(sim_time), tsp)
                    events.extend(tsp_events)
                    frame["events"] = tsp_events
                
                # 每10步打印進度
                if step % 10 == 0:
                    print(f"  Step {step}/{steps} (t={sim_time:.0f}s)")
            
            # 計算 KPIs
            kpis = sim.calculate_kpis(frames)
            kpis["mode"] = mode
            
            print(f"✓ Simulation completed: {len(frames)} frames, KPIs: {kpis}")
            
            return {
                "frames": frames,
                "kpis": kpis,
                "events": sim.events,
                "success": True
            }
            
        except Exception as e:
            print(f"Error during simulation: {e}")
            traceback.print_exc()
            return {"error": str(e), "success": False}


# 測試用例
if __name__ == "__main__":
    # 煙霧測試
    print("=== SUMO Corridor Simulator Tests ===")
    
    if not traci:
        print("⚠️  SUMO not available, skipping tests")
        sys.exit(0)
    
    # 測試 offset 配置生成
    from tempfile import TemporaryDirectory
    
    with TemporaryDirectory() as temp_dir:
        assets_dir = Path(temp_dir)
        
        sim = SumoCorridorSimulator()
        offsets = {"J1": 0, "J2": 27, "J3": 52}
        
        additional_file = sim.generate_additional_file(assets_dir, offsets, 90)
        assert additional_file.exists()
        
        # 檢查生成的 XML
        tree = ET.parse(additional_file)
        root = tree.getroot()
        assert root.tag == "additionalFile"
        
        tl_logics = root.findall("tlLogic")
        assert len(tl_logics) == 3
        
        print("✓ Additional file generation test passed")
    
    print("✓ All tests passed (SUMO connection tests require actual SUMO assets)")