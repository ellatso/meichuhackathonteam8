"""
Transit Signal Priority (TSP) for Anti-Bunching
公車不群聚控制：基於頭距 (headway) 的信號優先策略
"""

import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class TSPDecision:
    """TSP 決策結果"""
    grant: bool = False
    extend: int = 0  # 延綠秒數
    advance: int = 0  # 提前綠秒數 
    hold: int = 0  # 站點保留秒數
    reason: str = ""


class TSPController:
    """
    TSP 控制器 - 管理每個號誌的冷卻狀態
    """
    
    def __init__(self):
        self.last_grant_time: Dict[str, float] = {}  # 每個號誌的最後授予時間
        self.total_extensions: Dict[str, int] = {}  # 每個週期的累計延長時間
        self.cycle_start_time: Dict[str, float] = {}  # 週期開始時間
    
    def reset_cycle(self, tls_id: str, current_time: float):
        """重置週期計數器"""
        self.cycle_start_time[tls_id] = current_time
        self.total_extensions[tls_id] = 0
    
    def can_grant_tsp(self, tls_id: str, current_time: float, cooldown: int = 60) -> bool:
        """檢查是否可以授予 TSP (考慮冷卻時間)"""
        last_time = self.last_grant_time.get(tls_id, 0)
        return (current_time - last_time) >= cooldown
    
    def get_cycle_extensions(self, tls_id: str) -> int:
        """獲取當前週期的累計延長時間"""
        return self.total_extensions.get(tls_id, 0)
    
    def record_grant(self, tls_id: str, current_time: float, extend_sec: int = 0):
        """記錄 TSP 授予"""
        self.last_grant_time[tls_id] = current_time
        current_ext = self.total_extensions.get(tls_id, 0)
        self.total_extensions[tls_id] = current_ext + extend_sec


def tsp_policy(
    h_now: float,
    H: float = 360,  # 目標頭距 (秒)
    delta: float = 90,  # 容忍範圍 (秒)
    max_ext: int = 8,  # 最大延綠 (秒)
    max_adv: int = 6,  # 最大提前綠 (秒)
    cooldown: int = 60  # 冷卻時間 (秒)
) -> TSPDecision:
    """
    頭距驅動的 TSP 決策邏輯
    
    Args:
        h_now: 當前頭距 (秒)
        H: 目標頭距 (秒，預設 6 分鐘)
        delta: 容忍範圍 (秒)
        max_ext: 最大延綠時間
        max_adv: 最大提前綠時間
        cooldown: 冷卻時間
        
    Returns:
        TSPDecision 物件
        
    Examples:
        >>> # 晚點情況 (頭距過大)
        >>> decision = tsp_policy(480, 360, 90)  # h_now=8min, H=6min, delta=1.5min
        >>> assert decision.grant == True
        >>> assert decision.extend > 0
        
        >>> # 要群聚情況 (頭距過小)  
        >>> decision = tsp_policy(240, 360, 90)  # h_now=4min < H-delta=4.5min
        >>> assert decision.grant == False
        >>> assert decision.hold > 0
        
        >>> # 正常情況
        >>> decision = tsp_policy(360, 360, 90)  # h_now = H
        >>> assert decision.grant == False
        >>> assert decision.extend == 0 and decision.hold == 0
    """
    
    decision = TSPDecision()
    
    # 晚點 / 頭距過大 → 給予 TSP 優先
    if h_now > H + delta:
        decision.grant = True
        decision.extend = max_ext  # 給予最大延綠
        decision.advance = max_adv  # 允許提前綠
        decision.hold = 0
        decision.reason = f"Late bus: headway {h_now:.0f}s > {H+delta:.0f}s"
        
    # 過早 / 要群聚 → 拒絕 TSP，考慮站點保留
    elif h_now < H - delta:
        decision.grant = False
        decision.extend = 0
        decision.advance = 0
        decision.hold = 15  # 站點保留 15 秒
        decision.reason = f"Early bus: headway {h_now:.0f}s < {H-delta:.0f}s"
        
    # 正常範圍 → 不需要 TSP
    else:
        decision.grant = False
        decision.extend = 0
        decision.advance = 0
        decision.hold = 0
        decision.reason = f"Normal headway: {h_now:.0f}s within [{H-delta:.0f}, {H+delta:.0f}]s"
    
    return decision


def calculate_headway(bus_times: list, target_bus_id: str = None) -> float:
    """
    計算當前公車的頭距
    
    Args:
        bus_times: [(bus_id, timestamp), ...] 按時間排序的公車通過記錄
        target_bus_id: 目標公車 ID，如果為 None 則計算最後兩台的頭距
        
    Returns:
        頭距 (秒)，如果無法計算則返回目標頭距
    """
    if len(bus_times) < 2:
        return 360  # 預設目標頭距
    
    if target_bus_id:
        # 找到目標公車和前一台公車的時間
        target_idx = None
        for i, (bus_id, _) in enumerate(bus_times):
            if bus_id == target_bus_id:
                target_idx = i
                break
        
        if target_idx is None or target_idx == 0:
            return 360
        
        current_time = bus_times[target_idx][1]
        previous_time = bus_times[target_idx - 1][1]
        return current_time - previous_time
    else:
        # 計算最後兩台公車的頭距
        return bus_times[-1][1] - bus_times[-2][1]


def apply_tsp_to_phase(
    current_green_remaining: int,
    current_cycle_extensions: int,
    decision: TSPDecision,
    min_green: int = 10,
    max_cycle_extension: int = 10
) -> Tuple[int, bool]:
    """
    將 TSP 決策應用到實際相位控制
    
    Args:
        current_green_remaining: 當前綠燈剩餘時間
        current_cycle_extensions: 本週期已延長時間
        decision: TSP 決策
        min_green: 最小綠燈時間 (保護側向交通)
        max_cycle_extension: 每週期最大延長時間
        
    Returns:
        (實際延長秒數, 是否成功授予)
    """
    if not decision.grant:
        return 0, False
    
    # 檢查週期延長上限
    remaining_budget = max_cycle_extension - current_cycle_extensions
    if remaining_budget <= 0:
        return 0, False
    
    # 計算實際可延長時間
    requested_extension = decision.extend
    actual_extension = min(requested_extension, remaining_budget)
    
    # 確保不會過度延長
    if actual_extension <= 0:
        return 0, False
    
    return actual_extension, True


# 測試用例
if __name__ == "__main__":
    print("=== TSP Policy Tests ===")
    
    # 測試案例 1: 晚點公車
    print("\n1. Late Bus Test:")
    decision = tsp_policy(h_now=480, H=360, delta=90)  # 8min headway, target 6min
    print(f"   Headway: 480s (8min), Decision: {decision}")
    assert decision.grant == True
    assert decision.extend > 0
    
    # 測試案例 2: 早到公車 (要群聚)
    print("\n2. Early Bus Test:")
    decision = tsp_policy(h_now=240, H=360, delta=90)  # 4min headway
    print(f"   Headway: 240s (4min), Decision: {decision}")
    assert decision.grant == False
    assert decision.hold > 0
    
    # 測試案例 3: 正常頭距
    print("\n3. Normal Headway Test:")
    decision = tsp_policy(h_now=360, H=360, delta=90)  # exactly on target
    print(f"   Headway: 360s (6min), Decision: {decision}")
    assert decision.grant == False
    assert decision.extend == 0 and decision.hold == 0
    
    # 測試 TSP Controller
    print("\n=== TSP Controller Tests ===")
    controller = TSPController()
    current_time = time.time()
    
    # 第一次授予應該成功
    can_grant_1 = controller.can_grant_tsp("J1", current_time, cooldown=60)
    print(f"First grant attempt: {can_grant_1}")
    assert can_grant_1 == True
    
    controller.record_grant("J1", current_time, extend_sec=5)
    
    # 冷卻期內不應該授予
    can_grant_2 = controller.can_grant_tsp("J1", current_time + 30, cooldown=60)
    print(f"Grant during cooldown: {can_grant_2}")
    assert can_grant_2 == False
    
    # 冷卻期後應該可以授予
    can_grant_3 = controller.can_grant_tsp("J1", current_time + 70, cooldown=60)
    print(f"Grant after cooldown: {can_grant_3}")
    assert can_grant_3 == True
    
    print("\n✓ All TSP tests passed!")