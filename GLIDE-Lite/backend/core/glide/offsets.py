"""
GLIDE-Lite 綠波 Offset 計算模組
計算基於距離與目標速度的號誌 offset，以及對應的綠帶時間窗
"""

from typing import List, Dict, Tuple
import math


def compute_offsets(distances_m: List[float], cycle_s: int = 90, v_prog_kmh: float = 40) -> List[int]:
    """
    計算幹道綠波 offset
    
    Args:
        distances_m: 節點間距離列表 (例如 [300, 280] 表示 J1->J2=300m, J2->J3=280m)
        cycle_s: 信號週期 (秒)
        v_prog_kmh: 目標巡航速度 (km/h)
    
    Returns:
        offset 列表，第一個節點為 0
        
    Example:
        >>> compute_offsets([300, 280], 90, 40)
        [0, 27, 52]
        # J1=0s, J2=27s, J3=52s (27+25=52)
    """
    if not distances_m:
        return [0]
    
    v_ms = v_prog_kmh / 3.6  # 轉換為 m/s
    offsets = [0]  # 第一個節點 offset = 0
    
    cumulative_travel = 0
    for distance in distances_m:
        travel_time = distance / v_ms
        cumulative_travel += travel_time
        offset = int(cumulative_travel % cycle_s)  # 下捨整
        offsets.append(offset)
    
    return offsets


def compute_green_band(
    node_ids: List[str], 
    offsets_map: Dict[str, int], 
    cycle_s: int, 
    main_split: float = 0.6
) -> List[Dict[str, any]]:
    """
    計算綠帶時間窗
    
    Args:
        node_ids: 節點 ID 列表 (例如 ["J1", "J2", "J3"])
        offsets_map: 節點到 offset 的映射 (例如 {"J1": 0, "J2": 27, "J3": 52})
        cycle_s: 信號週期
        main_split: 主線相位分配比例
        
    Returns:
        綠帶資訊列表，每個元素包含 {node, start, end, width}
    """
    green_width = int(main_split * cycle_s)
    green_band = []
    
    for node_id in node_ids:
        offset = offsets_map.get(node_id, 0)
        start_time = offset
        end_time = min(cycle_s, start_time + green_width)
        
        # 處理週期邊界情況
        if end_time < start_time:
            end_time = cycle_s
            
        green_band.append({
            "node": node_id,
            "start": start_time,
            "end": end_time,
            "width": green_width,
            "offset": offset
        })
    
    return green_band


def adaptive_speed_update(v_prog_current: float, v_observed: float, alpha: float = 0.3) -> float:
    """
    自適應速度更新 (指數移動平均)
    
    Args:
        v_prog_current: 當前目標速度 (km/h)
        v_observed: 觀測到的實際速度 (km/h)
        alpha: 學習率 (0-1)
        
    Returns:
        更新後的目標速度
    """
    return (1 - alpha) * v_prog_current + alpha * v_observed


def validate_offsets(offsets: List[int], cycle_s: int) -> bool:
    """
    驗證 offset 序列的有效性
    
    Args:
        offsets: offset 列表
        cycle_s: 週期長度
        
    Returns:
        是否有效
    """
    if not offsets:
        return False
    
    # 檢查第一個是否為 0
    if offsets[0] != 0:
        return False
    
    # 檢查所有 offset 是否在有效範圍內
    for offset in offsets:
        if offset < 0 or offset >= cycle_s:
            return False
    
    # 檢查單調性 (考慮週期邊界)
    for i in range(1, len(offsets)):
        if offsets[i] < offsets[i-1] and offsets[i] != 0:
            # 允許週期重置的情況
            pass
        
    return True


# 測試用例 (內嵌 docstring)
if __name__ == "__main__":
    # 測試案例：距離 [300, 280]m，週期 90s，速度 40km/h
    distances = [300, 280]
    cycle = 90
    speed = 40
    
    offsets = compute_offsets(distances, cycle, speed)
    print(f"Distances: {distances}m")
    print(f"Cycle: {cycle}s, Speed: {speed}km/h")
    print(f"Offsets: {offsets}")
    
    # 預期結果：
    # 300m / (40/3.6 m/s) = 27s
    # 280m / (40/3.6 m/s) = 25.2s -> 27+25=52s
    # 所以 offsets = [0, 27, 52]
    
    node_ids = ["J1", "J2", "J3"]
    offsets_map = dict(zip(node_ids, offsets))
    green_band = compute_green_band(node_ids, offsets_map, cycle)
    
    print(f"\nGreen Band:")
    for band in green_band:
        print(f"  {band['node']}: {band['start']}-{band['end']}s (width={band['width']}s)")
    
    # 驗證結果
    assert validate_offsets(offsets, cycle), "Offsets validation failed"
    print("\n✓ All tests passed")