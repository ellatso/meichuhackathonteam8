"""
GLIDE-Lite Offsets 計算模組測試
測試綠波 offset 計算的正確性與邊界條件
"""

import pytest
import sys
from pathlib import Path

# 添加 backend 模組路徑
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

try:
    from core.glide.offsets import (
        compute_offsets,
        compute_green_band,
        adaptive_speed_update,
        validate_offsets
    )
except ImportError as e:
    pytest.skip(f"Cannot import offsets module: {e}", allow_module_level=True)


class TestComputeOffsets:
    """測試 offset 計算功能"""
    
    def test_basic_offsets_calculation(self):
        """測試基本 offset 計算"""
        # 標準案例：距離 [300, 280]m，週期 90s，速度 40km/h
        distances = [300, 280]
        cycle = 90
        speed = 40
        
        offsets = compute_offsets(distances, cycle, speed)
        
        # 驗證基本屬性
        assert len(offsets) == 3  # 3個節點
        assert offsets[0] == 0   # 第一個節點必須為 0
        assert all(0 <= offset < cycle for offset in offsets)  # 在有效範圍內
        
        # 預期計算結果
        # 300m / (40/3.6 m/s) ≈ 27s
        # 280m / (40/3.6 m/s) ≈ 25.2s → 累積 52.2s → 52s (下捨整)
        expected_offsets = [0, 27, 52]
        assert offsets == expected_offsets
    
    def test_empty_distances(self):
        """測試空距離列表"""
        offsets = compute_offsets([])
        assert offsets == [0]
    
    def test_single_distance(self):
        """測試單一距離"""
        distances = [500]
        offsets = compute_offsets(distances, cycle_s=120, v_prog_kmh=50)
        
        assert len(offsets) == 2
        assert offsets[0] == 0
        
        # 500m / (50/3.6 m/s) ≈ 36s
        expected_second = int(500 / (50/3.6))
        assert offsets[1] == expected_second
    
    def test_cycle_wraparound(self):
        """測試週期邊界情況"""
        # 長距離導致 offset 超過週期
        distances = [1000, 1000]  # 很長的距離
        cycle = 60  # 短週期
        speed = 30  # 慢速度
        
        offsets = compute_offsets(distances, cycle, speed)
        
        assert len(offsets) == 3
        assert offsets[0] == 0
        assert all(0 <= offset < cycle for offset in offsets)
    
    def test_different_speeds(self):
        """測試不同速度的影響"""
        distances = [300, 300]
        cycle = 90
        
        # 慢速
        offsets_slow = compute_offsets(distances, cycle, v_prog_kmh=20)
        # 快速
        offsets_fast = compute_offsets(distances, cycle, v_prog_kmh=60)
        
        # 慢速應該有更大的 offset
        assert offsets_slow[1] > offsets_fast[1]
        assert offsets_slow[2] > offsets_fast[2]
    
    def test_monotonicity(self):
        """測試 offset 的單調性 (考慮週期)"""
        distances = [200, 300, 250]
        offsets = compute_offsets(distances)
        
        # 檢查累積行程時間的單調性
        v_ms = 40 / 3.6
        cumulative_times = [0]
        for d in distances:
            cumulative_times.append(cumulative_times[-1] + d / v_ms)
        
        # 未取模前應該是單調遞增的
        assert all(cumulative_times[i] <= cumulative_times[i+1] 
                  for i in range(len(cumulative_times)-1))


class TestComputeGreenBand:
    """測試綠帶計算功能"""
    
    def test_basic_green_band(self):
        """測試基本綠帶計算"""
        node_ids = ["J1", "J2", "J3"]
        offsets_map = {"J1": 0, "J2": 27, "J3": 52}
        cycle = 90
        main_split = 0.6
        
        green_band = compute_green_band(node_ids, offsets_map, cycle, main_split)
        
        assert len(green_band) == 3
        
        for i, band in enumerate(green_band):
            assert band["node"] == node_ids[i]
            assert band["offset"] == offsets_map[node_ids[i]]
            assert band["width"] == int(cycle * main_split)  # 54s
            assert band["start"] == offsets_map[node_ids[i]]
            assert band["end"] <= cycle
    
    def test_green_band_with_different_splits(self):
        """測試不同 split 比例的綠帶"""
        node_ids = ["J1", "J2"]
        offsets_map = {"J1": 0, "J2": 30}
        cycle = 90
        
        # 測試不同的 main_split
        for split in [0.4, 0.6, 0.8]:
            green_band = compute_green_band(node_ids, offsets_map, cycle, split)
            
            expected_width = int(cycle * split)
            for band in green_band:
                assert band["width"] == expected_width
    
    def test_green_band_boundary_conditions(self):
        """測試綠帶邊界條件"""
        node_ids = ["J1"]
        offsets_map = {"J1": 80}  # 接近週期末尾
        cycle = 90
        main_split = 0.7  # 63s 綠燈
        
        green_band = compute_green_band(node_ids, offsets_map, cycle, main_split)
        
        band = green_band[0]
        assert band["start"] == 80
        assert band["end"] == 90  # 不能超過週期
        assert band["width"] == int(cycle * main_split)


class TestAdaptiveSpeedUpdate:
    """測試自適應速度更新"""
    
    def test_speed_adaptation(self):
        """測試速度自適應算法"""
        current_speed = 40.0
        observed_speed = 35.0
        alpha = 0.3
        
        new_speed = adaptive_speed_update(current_speed, observed_speed, alpha)
        
        # 應該介於兩個速度之間
        assert min(current_speed, observed_speed) <= new_speed <= max(current_speed, observed_speed)
        
        # 驗證指數移動平均公式
        expected = (1 - alpha) * current_speed + alpha * observed_speed
        assert abs(new_speed - expected) < 1e-6
    
    def test_speed_adaptation_extremes(self):
        """測試極端情況下的速度適應"""
        # alpha = 0 (不更新)
        new_speed = adaptive_speed_update(40, 20, alpha=0)
        assert new_speed == 40
        
        # alpha = 1 (完全跟隨觀測值)
        new_speed = adaptive_speed_update(40, 20, alpha=1)
        assert new_speed == 20


class TestValidateOffsets:
    """測試 offset 驗證功能"""
    
    def test_valid_offsets(self):
        """測試有效的 offset 序列"""
        # 正常情況
        assert validate_offsets([0, 20, 45], 90) == True
        
        # 單一節點
        assert validate_offsets([0], 90) == True
    
    def test_invalid_offsets(self):
        """測試無效的 offset 序列"""
        # 空列表
        assert validate_offsets([], 90) == False
        
        # 第一個不為 0
        assert validate_offsets([10, 20, 30], 90) == False
        
        # 超出週期範圍
        assert validate_offsets([0, 50, 100], 90) == False
        
        # 負數
        assert validate_offsets([0, -10, 20], 90) == False


class TestIntegration:
    """整合測試"""
    
    def test_complete_workflow(self):
        """測試完整的計算流程"""
        # 模擬真實的 3 路口廊道
        distances = [300, 280]  # J1-J2, J2-J3
        cycle = 90
        speed = 40
        
        # 1. 計算 offsets
        offsets_list = compute_offsets(distances, cycle, speed)
        assert validate_offsets(offsets_list, cycle)
        
        # 2. 建立映射
        node_ids = ["J1", "J2", "J3"]
        offsets_map = dict(zip(node_ids, offsets_list))
        
        # 3. 計算綠帶
        green_band = compute_green_band(node_ids, offsets_map, cycle)
        
        # 4. 驗證結果一致性
        assert len(green_band) == len(node_ids)
        for i, band in enumerate(green_band):
            assert band["node"] == node_ids[i]
            assert band["offset"] == offsets_list[i]
    
    def test_performance_with_many_nodes(self):
        """測試大量節點的性能"""
        # 模擬長廊道 (10個節點)
        distances = [300] * 9  # 9段距離，10個節點
        
        import time
        start_time = time.time()
        offsets = compute_offsets(distances)
        end_time = time.time()
        
        # 應該很快完成 (< 0.1秒)
        assert end_time - start_time < 0.1
        assert len(offsets) == 10
        assert validate_offsets(offsets, 90)


# 參數化測試
@pytest.mark.parametrize("distances,cycle,speed,expected_first_offset", [
    ([400], 120, 40, 36),  # 400m / (40/3.6) ≈ 36s
    ([600], 90, 60, 36),   # 600m / (60/3.6) ≈ 36s
    ([200], 60, 30, 24),   # 200m / (30/3.6) ≈ 24s
])
def test_parameterized_offsets(distances, cycle, speed, expected_first_offset):
    """參數化測試不同場景"""
    offsets = compute_offsets(distances, cycle, speed)
    assert len(offsets) == len(distances) + 1
    assert offsets[0] == 0
    assert offsets[1] == expected_first_offset


if __name__ == "__main__":
    # 直接運行測試
    pytest.main([__file__, "-v"])