"""
GLIDE-Lite TSP (Transit Signal Priority) 模組測試
測試公車不群聚控制邏輯的正確性
"""

import pytest
import time
import sys
from pathlib import Path

# 添加 backend 模組路徑
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

try:
    from core.glide.tsp import (
        tsp_policy,
        TSPController,
        TSPDecision,
        calculate_headway,
        apply_tsp_to_phase
    )
except ImportError as e:
    pytest.skip(f"Cannot import TSP module: {e}", allow_module_level=True)


class TestTSPPolicy:
    """測試 TSP 決策邏輯"""
    
    def test_late_bus_scenario(self):
        """測試晚點公車情況 (頭距過大)"""
        H = 360  # 目標 6 分鐘
        delta = 90  # 1.5 分鐘容忍範圍
        h_now = 480  # 實際 8 分鐘 → 晚點
        
        decision = tsp_policy(h_now, H, delta)
        
        assert decision.grant == True
        assert decision.extend > 0
        assert decision.hold == 0
        assert "Late bus" in decision.reason
    
    def test_early_bus_scenario(self):
        """測試早到公車情況 (要群聚)"""
        H = 360  # 目標 6 分鐘
        delta = 90  # 1.5 分鐘容忍範圍
        h_now = 240  # 實際 4 分鐘 → 過早
        
        decision = tsp_policy(h_now, H, delta)
        
        assert decision.grant == False
        assert decision.extend == 0
        assert decision.hold > 0
        assert "Early bus" in decision.reason
    
    def test_normal_headway_scenario(self):
        """測試正常頭距情況"""
        H = 360
        delta = 90
        h_now = 360  # 正好符合目標
        
        decision = tsp_policy(h_now, H, delta)
        
        assert decision.grant == False
        assert decision.extend == 0
        assert decision.hold == 0
        assert "Normal headway" in decision.reason
    
    def test_boundary_conditions(self):
        """測試邊界條件"""
        H = 360
        delta = 90
        
        # 邊界：H + delta (450s)
        decision_boundary_high = tsp_policy(H + delta, H, delta)
        assert decision_boundary_high.grant == False  # 等於邊界，不觸發
        
        decision_over_boundary = tsp_policy(H + delta + 1, H, delta)
        assert decision_over_boundary.grant == True  # 超過邊界，觸發
        
        # 邊界：H - delta (270s)
        decision_boundary_low = tsp_policy(H - delta, H, delta)
        assert decision_boundary_low.grant == False  # 等於邊界，不觸發
        
        decision_under_boundary = tsp_policy(H - delta - 1, H, delta)
        assert decision_under_boundary.grant == False  # 低於邊界，不給TSP但要保留
        assert decision_under_boundary.hold > 0
    
    def test_custom_parameters(self):
        """測試自訂參數"""
        decision = tsp_policy(
            h_now=500,
            H=300,
            delta=60,
            max_ext=12,
            max_adv=8
        )
        
        assert decision.grant == True
        assert decision.extend == 12  # 使用自訂最大延長
        assert decision.advance == 8   # 使用自訂最大提前


class TestTSPController:
    """測試 TSP 控制器"""
    
    def test_controller_initialization(self):
        """測試控制器初始化"""
        controller = TSPController()
        
        assert len(controller.last_grant_time) == 0
        assert len(controller.total_extensions) == 0
        assert len(controller.cycle_start_time) == 0
    
    def test_cooldown_mechanism(self):
        """測試冷卻機制"""
        controller = TSPController()
        current_time = time.time()
        tls_id = "J1"
        
        # 第一次應該可以授予
        assert controller.can_grant_tsp(tls_id, current_time, cooldown=60) == True
        
        # 記錄授予
        controller.record_grant(tls_id, current_time, extend_sec=5)
        
        # 冷卻期內不應該授予
        assert controller.can_grant_tsp(tls_id, current_time + 30, cooldown=60) == False
        
        # 冷卻期後應該可以授予
        assert controller.can_grant_tsp(tls_id, current_time + 70, cooldown=60) == True
    
    def test_cycle_extension_tracking(self):
        """測試週期延長追蹤"""
        controller = TSPController()
        tls_id = "J1"
        current_time = time.time()
        
        # 重置週期
        controller.reset_cycle(tls_id, current_time)
        assert controller.get_cycle_extensions(tls_id) == 0
        
        # 記錄延長
        controller.record_grant(tls_id, current_time, extend_sec=5)
        assert controller.get_cycle_extensions(tls_id) == 5
        
        # 累積延長
        controller.record_grant(tls_id, current_time + 30, extend_sec=3)
        assert controller.get_cycle_extensions(tls_id) == 8
        
        # 重置週期應該清零
        controller.reset_cycle(tls_id, current_time + 90)
        assert controller.get_cycle_extensions(tls_id) == 0
    
    def test_multiple_tls_independence(self):
        """測試多個號誌的獨立性"""
        controller = TSPController()
        current_time = time.time()
        
        # 為 J1 授予
        controller.record_grant("J1", current_time, extend_sec=5)
        
        # J2 應該不受影響
        assert controller.can_grant_tsp("J2", current_time, cooldown=60) == True
        assert controller.get_cycle_extensions("J2") == 0
        
        # J1 在冷卻期內
        assert controller.can_grant_tsp("J1", current_time + 30, cooldown=60) == False


class TestCalculateHeadway:
    """測試頭距計算"""
    
    def test_basic_headway_calculation(self):
        """測試基本頭距計算"""
        bus_times = [
            ("bus_1", 100),
            ("bus_2", 460)  # 460 - 100 = 360s
        ]
        
        headway = calculate_headway(bus_times)
        assert headway == 360
    
    def test_insufficient_data(self):
        """測試數據不足的情況"""
        # 只有一台公車
        bus_times = [("bus_1", 100)]
        headway = calculate_headway(bus_times)
        assert headway == 360  # 返回預設值
        
        # 空列表
        headway = calculate_headway([])
        assert headway == 360
    
    def test_target_bus_headway(self):
        """測試指定公車的頭距計算"""
        bus_times = [
            ("bus_1", 100),
            ("bus_2", 460),
            ("bus_3", 820)
        ]
        
        # 計算 bus_2 的頭距
        headway = calculate_headway(bus_times, target_bus_id="bus_2")
        assert headway == 360  # 460 - 100
        
        # 計算 bus_3 的頭距
        headway = calculate_headway(bus_times, target_bus_id="bus_3")
        assert headway == 360  # 820 - 460
        
        # 不存在的公車 ID
        headway = calculate_headway(bus_times, target_bus_id="bus_4")
        assert headway == 360  # 返回預設值
    
    def test_multiple_buses(self):
        """測試多台公車的頭距計算"""
        bus_times = [
            ("bus_1", 60),
            ("bus_2", 420),   # 360s 頭距
            ("bus_3", 750),   # 330s 頭距
            ("bus_4", 1110)   # 360s 頭距
        ]
        
        # 預設計算最後兩台的頭距
        headway = calculate_headway(bus_times)
        assert headway == 360  # 1110 - 750


class TestApplyTspToPhase:
    """測試 TSP 應用到相位控制"""
    
    def test_successful_extension(self):
        """測試成功延長"""
        decision = TSPDecision(grant=True, extend=8, advance=0, hold=0)
        current_extensions = 2  # 本週期已延長 2 秒
        
        actual_ext, granted = apply_tsp_to_phase(
            current_green_remaining=30,
            current_cycle_extensions=current_extensions,
            decision=decision,
            max_cycle_extension=10
        )
        
        assert granted == True
        assert actual_ext == 8  # 2 + 8 = 10，在上限內
    
    def test_extension_budget_exceeded(self):
        """測試延長預算超限"""
        decision = TSPDecision(grant=True, extend=8, advance=0, hold=0)
        current_extensions = 8  # 本週期已延長 8 秒
        
        actual_ext, granted = apply_tsp_to_phase(
            current_green_remaining=30,
            current_cycle_extensions=current_extensions,
            decision=decision,
            max_cycle_extension=10
        )
        
        assert granted == True
        assert actual_ext == 2  # 只能再延長 2 秒 (10 - 8)
    
    def test_budget_exhausted(self):
        """測試預算耗盡"""
        decision = TSPDecision(grant=True, extend=5, advance=0, hold=0)
        current_extensions = 10  # 預算已用完
        
        actual_ext, granted = apply_tsp_to_phase(
            current_green_remaining=30,
            current_cycle_extensions=current_extensions,
            decision=decision,
            max_cycle_extension=10
        )
        
        assert granted == False
        assert actual_ext == 0
    
    def test_no_grant_decision(self):
        """測試不授予 TSP 的情況"""
        decision = TSPDecision(grant=False, extend=0, advance=0, hold=15)
        
        actual_ext, granted = apply_tsp_to_phase(
            current_green_remaining=30,
            current_cycle_extensions=0,
            decision=decision
        )
        
        assert granted == False
        assert actual_ext == 0


class TestTSPDecision:
    """測試 TSP 決策結構"""
    
    def test_decision_creation(self):
        """測試決策物件創建"""
        decision = TSPDecision()
        
        assert decision.grant == False
        assert decision.extend == 0
        assert decision.advance == 0
        assert decision.hold == 0
        assert decision.reason == ""
    
    def test_decision_with_values(self):
        """測試帶值的決策物件"""
        decision = TSPDecision(
            grant=True,
            extend=8,
            advance=5,
            hold=0,
            reason="Test case"
        )
        
        assert decision.grant == True
        assert decision.extend == 8
        assert decision.advance == 5
        assert decision.hold == 0
        assert decision.reason == "Test case"


class TestIntegrationScenarios:
    """整合測試場景"""
    
    def test_complete_tsp_workflow(self):
        """測試完整的 TSP 工作流程"""
        controller = TSPController()
        tls_id = "J1"
        current_time = time.time()
        
        # 場景：晚點公車需要 TSP
        bus_times = [
            ("bus_1", current_time - 600),  # 10 分鐘前
            ("bus_2", current_time)         # 現在 → 頭距 600s (10min)
        ]
        
        # 1. 計算頭距
        headway = calculate_headway(bus_times)
        assert headway == 600
        
        # 2. TSP 決策
        decision = tsp_policy(headway, H=360, delta=90)
        assert decision.grant == True
        
        # 3. 檢查冷卻
        can_grant = controller.can_grant_tsp(tls_id, current_time)
        assert can_grant == True
        
        # 4. 應用到相位
        actual_ext, granted = apply_tsp_to_phase(
            current_green_remaining=20,
            current_cycle_extensions=0,
            decision=decision
        )
        assert granted == True
        assert actual_ext > 0
        
        # 5. 記錄授予
        controller.record_grant(tls_id, current_time, actual_ext)
        
        # 6. 驗證冷卻生效
        assert controller.can_grant_tsp(tls_id, current_time + 30) == False
    
    def test_anti_bunching_scenario(self):
        """測試防群聚場景"""
        # 場景：兩台公車相隔太近
        bus_times = [
            ("bus_1", 100),
            ("bus_2", 220)  # 只間隔 120s (2min) → 要群聚
        ]
        
        headway = calculate_headway(bus_times)
        decision = tsp_policy(headway, H=360, delta=90)
        
        # 應該拒絕 TSP 並建議保留
        assert decision.grant == False
        assert decision.hold > 0
        assert "Early bus" in decision.reason
    
    def test_rush_hour_scenario(self):
        """測試尖峰時段場景 (較短目標頭距)"""
        # 尖峰時段：目標頭距 4 分鐘
        H_rush = 240
        delta = 60
        
        # 正常情況下可能觸發的頭距，在尖峰時段是正常的
        h_now = 300  # 5 分鐘
        
        decision = tsp_policy(h_now, H=H_rush, delta=delta)
        assert decision.grant == True  # 300 > 240 + 60
        
        # 較短的頭距在尖峰時段是正常的
        h_now = 210  # 3.5 分鐘
        decision = tsp_policy(h_now, H=H_rush, delta=delta)
        assert decision.grant == False  # 在正常範圍內


# 參數化測試
@pytest.mark.parametrize("headway,H,delta,expected_grant,expected_hold", [
    (480, 360, 90, True, 0),   # 晚點：8min > 6min + 1.5min
    (240, 360, 90, False, 15), # 早到：4min < 6min - 1.5min
    (360, 360, 90, False, 0),  # 正常：正好 6min
    (420, 360, 90, False, 0),  # 正常：7min 在容忍範圍內
    (300, 360, 90, False, 0),  # 正常：5min 在容忍範圍內
])
def test_parameterized_tsp_decisions(headway, H, delta, expected_grant, expected_hold):
    """參數化測試不同頭距場景"""
    decision = tsp_policy(headway, H, delta)
    assert decision.grant == expected_grant
    assert (decision.hold > 0) == (expected_hold > 0)


if __name__ == "__main__":
    # 直接運行測試
    pytest.main([__file__, "-v"])