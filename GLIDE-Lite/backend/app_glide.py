from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import uuid, random, numpy as np


app = FastAPI(title="GLIDE-Lite API", version="1.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# ---------------- Utilities ----------------
def simple_compute_offsets(distances: List[float], cycle: int = 90, speed_kmh: float = 40) -> Dict[str, int]:
    """根據節點間距與巡航速度，計算綠波 offset。"""
    v = speed_kmh / 3.6
    offsets = {"J1": 0}
    acc = 0.0
    for i, d in enumerate(distances):
        acc += d / v
        offsets[f"J{i+2}"] = int(acc % cycle)
    return offsets

# ---------------- Models ----------------
class TSPParams(BaseModel):
    max_extend_sec: int = Field(10, ge=0, le=60)    # 最大延綠
    max_hold_sec:   int = Field(30, ge=0, le=120)   # 最大保留
    cooldown_sec:   int = Field(120, ge=0, le=600)  # 冷卻秒數

class BusLineSpec(BaseModel):
    id: str                         # 路線代號，例：R61, 235...
    headway_sec: int                # 班距（秒）
    jitter_sec: int = 40            # 發車抖動
    dwell_sec: int = 20             # 該線平均停站秒數
    phase_offset_sec: int = 0       # 初始相位，用來錯開多線同步到站

# 在 SimRequest 內 **新增**（其餘字段保留不變）
class SimRequest(BaseModel):
    mode: str = Field(..., pattern="^(fixed|glide|glide_tsp)$")
    steps: int = Field(180, ge=60, le=1800)
    cycle: int = Field(90, ge=30, le=180)
    v_prog_kmh: float = Field(40, ge=20, le=80)
    cars_per_hour: Optional[int] = Field(None, ge=0)

    bus_headway_sec: Optional[int] = Field(300, ge=60)  # 舊前端仍可用（單一路線時）
    ab_tolerance_sec: int = Field(120, ge=0)
    dwell_sec: int = Field(20, ge=0, le=120)
    simulate_bunching: bool = True
    anti_bunching: bool = True
    tsp: Optional[TSPParams] = None

    # ★ 新增：多路線公車
    bus_lines: Optional[List[BusLineSpec]] = None
class TSPParams(BaseModel):
    max_extend_sec: int = Field(10, ge=0, le=60)    # 最大延綠
    max_hold_sec:   int = Field(30, ge=0, le=120)   # 最大保留（延後發車）
    cooldown_sec:   int = Field(120, ge=0, le=600)  # TSP 冷卻

class PlanRequest(BaseModel):
    cycle: int = Field(90, ge=30, le=180)
    v_prog_kmh: float = Field(40, ge=20, le=80)

class SimRequest(BaseModel):
    mode: str = Field(..., pattern="^(fixed|glide|glide_tsp)$")
    steps: int = Field(180, ge=60, le=1800)
    cycle: int = Field(90, ge=30, le=180)
    v_prog_kmh: float = Field(40, ge=20, le=80)
    cars_per_hour: Optional[int] = Field(None, ge=0)     # 單向單車道 vph

    # 🚌 公車/Anti-Bunching/TSP 控制項（全都有預設，舊前端也能跑）
    bus_headway_sec: Optional[int] = Field(300, ge=60)   # 目標班距（秒）
    ab_tolerance_sec: int = Field(120, ge=0)            # 容忍範圍（±秒）
    dwell_sec: int = Field(20, ge=0, le=120)            # 站點停留秒數
    simulate_bunching: bool = True                      # 是否模擬群聚
    anti_bunching: bool = True                          # 是否啟用 Anti-Bunching
    tsp: Optional[TSPParams] = None                     # TSP 參數物件
    bus_lines: Optional[List[BusLineSpec]] = None

# ---------------- Endpoints ----------------
@app.get("/health")
async def health():
    return {"ok": True, "version": app.version}

@app.post("/glide/plan")
async def glide_plan(req: PlanRequest):
    distances = [300, 280]
    offsets = simple_compute_offsets(distances, req.cycle, req.v_prog_kmh)
    width = int(req.cycle * 0.6)
    band = [{"node": nid, "start": off, "end": min(req.cycle, off+width), "width": width}
            for nid, off in offsets.items()]
    return {"offsets": offsets, "green_band": band}
@app.post("/glide/sim")
async def run_sim(req: SimRequest):
    """
    多路線公車 + 站位容量 + 反群聚 + 監控回傳
    - 相容舊 payload；若不傳 bus_lines，會用羅斯福走廊風格預設。
    """
    try:
        session_id = f"sim_{uuid.uuid4().hex[:8]}"

        
        

        # ===== 基本參數 =====
        C = req.cycle
        G = int(0.6 * C)
        Y = 6
        V = req.v_prog_kmh / 3.6
        V_BUS = V * 0.9
        STEPS = int(min(req.steps, 1200))

        # 三個號誌（與前端畫面對齊的停止線座標）
        stoplines = {"J1": -600.0, "J2": -300.0, "J3": 0.0, "J4": 300.0, "J5": 600.0}
        nodes = list(stoplines.keys())

        # ===== KPI 聚合容器（實際觀測）=====
        car_exited = 0
        car_zero_stop = 0
        car_delay_sum = 0.0      # 累計信號延滯(秒)
        car_stops_sum = 0        # 累計信號停次
        car_travel_sum = 0.0     # 走廊旅行時間(秒)
        car_exit_ts: List[int] = []  # 出場時間序列，用來算放行頭距

# 每線公車延滯彙總（信號/站前/停靠）
        bus_delay_line: Dict[str, Dict[str, float]] = {}  # lid -> {"signal":秒, "queue":秒, "dwell":秒, "exited":數}

        # offsets：固定時制 -> 全 0；GLIDE -> 由距離/速度計算
        offsets = ({"J1": 0, "J2": 0, "J3": 0, "J4": 0, "J5": 0}
           if req.mode == "fixed"
           else simple_compute_offsets([300, 300, 300, 300], C, req.v_prog_kmh))

        # ===== 汽車流量（尖峰時視覺更密集） =====
        target_vph = req.cars_per_hour if req.cars_per_hour is not None else 1700
        mu_theory = (G * 3600.0 / C) / max(1, target_vph)  # 理論頭距（秒）
        if target_vph >= 2000:      mu_min, mu_max = 0.9, 2.2
        elif target_vph >= 1800:    mu_min, mu_max = 1.1, 2.5
        elif target_vph <= 800:     mu_min, mu_max = 2.8, 4.6
        else:                        mu_min, mu_max = 1.6, 3.2
        mu = float(np.clip(mu_theory, mu_min, mu_max))
        sigma = 0.25 if target_vph >= 1600 else 0.35

        def sample_headway():
            return float(np.clip(np.random.lognormal(mean=np.log(mu), sigma=sigma), 0.6, 6.0))

        # 綠窗內逐台出發（避免「一坨」）
        car_depart_times: List[float] = []
        k = 0
        while True:
            t0 = k * C - offsets["J1"]
            if t0 > STEPS:
                break
            t = max(0.0, t0) + random.uniform(0.25, 0.9)
            t_end = t0 + G

            # 高流量：綠窗早期注入 3 台貼靠的 platoon
            if target_vph >= 1800:
                t_burst = max(0.0, t0) + random.uniform(0.2, 0.6)
                for _ in range(3):
                    if t_burst < t_end and t_burst < STEPS:
                        car_depart_times.append(t_burst)
                        t_burst += random.uniform(0.35, 0.6)

            while t < t_end and t < STEPS:
                car_depart_times.append(t + random.uniform(-0.10, 0.10))
                t += sample_headway()
            k += 1
        car_depart_times.sort()

        # ====== 2-1 公車排程（多路線） ======
        lines: List[BusLineSpec] = req.bus_lines or [
            BusLineSpec(id="R61", headway_sec=240, jitter_sec=30, dwell_sec=25, phase_offset_sec=0),
            BusLineSpec(id="235", headway_sec=300, jitter_sec=35, dwell_sec=20, phase_offset_sec=60),
            BusLineSpec(id="236", headway_sec=300, jitter_sec=35, dwell_sec=22, phase_offset_sec=120),
            BusLineSpec(id="251", headway_sec=360, jitter_sec=40, dwell_sec=25, phase_offset_sec=180),
            BusLineSpec(id="252", headway_sec=420, jitter_sec=45, dwell_sec=25, phase_offset_sec=210),
            BusLineSpec(id="644", headway_sec=480, jitter_sec=50, dwell_sec=28, phase_offset_sec=240),
        ]

        schedule: Dict[str, List[float]] = {}
        for L in lines:
            times: List[float] = []
            first = max(5.0, min(15.0, 0.05 * STEPS)) + (L.phase_offset_sec % max(1, L.headway_sec))
            t_bus = first
            while t_bus < STEPS:
                times.append(t_bus)
                if req.simulate_bunching and random.random() < 0.25:
                    g = random.uniform(0.3 * L.headway_sec, 0.55 * L.headway_sec)
                    if t_bus + g < STEPS:
                        times.append(t_bus + g)
                jitter = random.uniform(-L.jitter_sec, L.jitter_sec)
                t_bus = max(0.0, t_bus + L.headway_sec + jitter)
            times.sort()
            schedule[L.id] = times

        # ====== 2-2 站點/容量 + 監控 ======
        #bus_stops = [-350.0, 750.0]   # 園區側 / 過橋後
        bus_stops = [-450.0, 450.0]

        stop_name = {bus_stops[0]: "S1_園區側", bus_stops[1]: "S2_竹北側"}
        STOP_BERTHS = 2

        monitor = {
            "lines": {L.id: {
                "scheduled_headway_sec": L.headway_sec,
                "arrivals": 0, "holds": 0, "tsp_extends": 0, "queue_holds": 0,
                "arr_times": [],
            } for L in lines},
            "stops": { stop_name[sx]: {"arrivals": 0, "avg_dwell": 0.0, "sum_dwell": 0.0,
                                       "queue_max": 0, "queue_now": 0} for sx in bus_stops }
        }
        stop_occupancy: Dict[float, List[str]] = {sx: [] for sx in bus_stops}
        stop_release_time: Dict[float, List[int]] = {sx: [] for sx in bus_stops}
        last_arrival_time: Dict[float, Optional[int]] = {sx: None for sx in bus_stops}

        # ====== 主回圈 ======
        def ew_state(nid: str, t_int: int) -> str:
            tau = (t_int + offsets.get(nid, 0)) % C
            if tau < G: return "G"
            if tau < G + Y: return "y"
            return "r"

        X_MIN, X_MAX = -800.0, 800.0
        vehicles: List[Dict[str, Any]] = []
        frames: List[Dict[str, Any]] = []
        events: List[Dict[str, Any]] = []
        arrived = 0
        car_i = 0
        bus_spawn_index: Dict[str, int] = {L.id: 0 for L in lines}

        COINCIDENCE_WINDOW = 18
        PRESTOP_HOLD = 16.0
        STOPLINE_BUFFER = 4.5

        def next_stopline_x(x_now: float):
            nxt = [sx for sx in stoplines.values() if sx > x_now + 0.1]
            return min(nxt) if nxt else None

        def update_one(v: Dict[str, Any], t_int: int, green_now: Dict[str, bool]):
            x, vel = v["x"], v["v"]
            x_try = x + vel

            # ----- 公車 -----
            if v["kind"] == "bus":
                # 仍在停靠
                if v.get("dwell_until") is not None:
                    if t_int < v["dwell_until"]:
                        v["stopped"] = True
                        v["stopped_at_station"] = True
                        v["x"] = x
                        return v
                    else:
                        sx0 = v.get("at_stop")
                        if sx0 is not None:
                            # 離站：釋放佔位
                            name = stop_name[sx0]
                            if v["id"] in stop_occupancy[sx0]:
                                i_rm = stop_occupancy[sx0].index(v["id"])
                                stop_occupancy[sx0].pop(i_rm)
                                stop_release_time[sx0].pop(i_rm)
                            v.setdefault("served_stops", []).append(sx0)
                            v["dwell_until"] = None
                            v.pop("stopped_at_station", None)
                            v.pop("at_stop", None)
                            x = max(x, sx0 + 0.2); x_try = max(x_try, sx0 + 0.2)
                            v["x"] = x

                # 檢查是否將跨越某站
                for sx in bus_stops:
                    if sx in v.get("served_stops", []):
                        pass
                    if x < sx <= x_try:
                        name = stop_name[sx]
                        occ = stop_occupancy[sx]
                        # 站位滿或短時間已有到站 → 站前 queue hold
                        if len(occ) >= STOP_BERTHS or (last_arrival_time[sx] is not None and (t_int - last_arrival_time[sx]) <= COINCIDENCE_WINDOW):
                            v["x"] = sx - PRESTOP_HOLD
                            v["stopped"] = True
                            v["queueing"] = True
                            monitor["lines"][v.get("line", "BUS")]["queue_holds"] += 1
                            return v

                        # 允許進站：開始 dwell
                        # 若有多線設定，用該線的專屬 dwell；否則用全域 dwell
                        dwell_cfg = req.dwell_sec
                        if req.bus_lines is not None:
                            for L in lines:
                                if L.id == v.get("line"):
                                    dwell_cfg = L.dwell_sec
                                    break
                        v["dwell_until"] = t_int + int(dwell_cfg)
                        v["at_stop"] = sx
                        v["x"] = sx - 0.1
                        v["stopped"] = True
                        v["stopped_at_station"] = True
                        v["queueing"] = False

                        # 佔位/監控
                        occ.append(v["id"])
                        stop_release_time[sx].append(v["dwell_until"])
                        last_arrival_time[sx] = t_int
                        mon_s = monitor["stops"][name]
                        mon_s["arrivals"] += 1
                        dwell_now = v["dwell_until"] - t_int
                        mon_s["sum_dwell"] += dwell_now
                        mon_s["avg_dwell"] = mon_s["sum_dwell"] / mon_s["arrivals"]
                        mon_s["queue_now"] = max(0, len(occ) - STOP_BERTHS)
                        mon_s["queue_max"] = max(mon_s["queue_max"], mon_s["queue_now"])
                        lid = v.get("line", "BUS")
                        monitor["lines"][lid]["arrivals"] += 1
                        monitor["lines"][lid]["arr_times"].append(t_int)
                        return v

            # ----- 紅/黃燈停止線限制（避免闖紅燈） -----
            sx_next = next_stopline_x(x)
            if sx_next is not None:
                nid = min(stoplines, key=lambda k: abs(stoplines[k] - sx_next))
                if not green_now.get(nid, False) and x < sx_next:
                    x_try = min(x_try, sx_next - STOPLINE_BUFFER)

            v["x"] = x_try
            v["stopped"] = (v["x"] == x)
            v.pop("stopped_at_station", None)
            return v

                # ===== 模擬時間步 =====
        for t in range(STEPS):
            # 進汽車
            while car_i < len(car_depart_times) and car_depart_times[car_i] < t + 1.0:
                dt = max(0.0, car_depart_times[car_i] - t)
                vehicles.append({
                    "id": f"car_{car_i}",
                    "x": X_MIN + V * dt,
                    "y": random.uniform(-2, 2),
                    "kind": "car",
                    "v": V * random.uniform(0.92, 1.05),
                    "stopped": False,
                    "enter_t": t + dt,
                    "stops_count": 0,
                    "delay_s": 0.0,
                })
                car_i += 1

            # 進公車（多路線）
            for L in lines:
                times = schedule[L.id]
                idx = bus_spawn_index[L.id]
                while idx < len(times) and times[idx] < t + 1.0:
                    dt = max(0.0, times[idx] - t)
                    vehicles.append({
                        "id": f"bus_{L.id}_{idx}",
                        "line": L.id,
                        "x": X_MIN + V_BUS * dt,
                        "y": 0.0,
                        "kind": "bus",
                        "v": V_BUS,
                        "stopped": False,
                        "dwell_until": None,
                        "served_stops": [],
                        "at_stop": None,
                        "queueing": False,
                        "enter_t": t + dt,
                        "signal_delay_s": 0.0,
                        "queue_hold_s": 0.0,
                        "dwell_s": 0.0,
                        "stops_count": 0,
                    })
                    idx += 1
                bus_spawn_index[L.id] = idx

            # 號誌
            signals = [{"node": nid, "state": ew_state(nid, t)} for nid in nodes]
            green_now = {s["node"]: (s["state"] == "G") for s in signals}

            # 主回圈內部：更新所有車輛、計分、出場
            moved: List[Dict[str, Any]] = []
            out_count = 0

            for v in sorted(vehicles, key=lambda z: 0 if z["kind"] == "bus" else 1):
                nv = update_one(v, t, green_now)

                # 每秒統計（依車種）
                if nv["kind"] == "car":
                    if nv.get("stopped", False):
                        nv["delay_s"] = nv.get("delay_s", 0.0) + 1.0
                else:  # bus
                    if nv.get("stopped_at_station"):
                        nv["dwell_s"] = nv.get("dwell_s", 0.0) + 1.0
                    elif nv.get("queueing"):
                        nv["queue_hold_s"] = nv.get("queue_hold_s", 0.0) + 1.0
                    elif nv.get("stopped", False):
                        nv["signal_delay_s"] = nv.get("signal_delay_s", 0.0) + 1.0

                # 出場處理
                if nv["x"] > X_MAX + 30:
                    out_count += 1
                    if nv["kind"] == "car":
                        car_exited += 1
                        if nv.get("stops_count", 0) == 0:
                            car_zero_stop += 1
                        car_delay_sum += nv.get("delay_s", 0.0)
                        car_stops_sum += nv.get("stops_count", 0)
                        car_travel_sum += (t + 1.0) - nv.get("enter_t", t + 1.0)
                        car_exit_ts.append(t + 1)
                    else:
                        lid = nv.get("line", "BUS")
                        d = bus_delay_line.setdefault(lid, {"signal": 0.0, "queue": 0.0, "dwell": 0.0, "exited": 0})
                        d["signal"] += nv.get("signal_delay_s", 0.0)
                        d["queue"]  += nv.get("queue_hold_s", 0.0)
                        d["dwell"]  += nv.get("dwell_s", 0.0)
                        d["exited"] += 1
                    continue  # 出場的不保留在場內

                moved.append(nv)

            vehicles = moved
            arrived += out_count

            # 渲染抽樣（公車全保留）
            buses = [v for v in vehicles if v["kind"] == "bus"]
            cars  = [v for v in vehicles if v["kind"] == "car"]
            render: List[Dict[str, Any]] = []
            render.extend({
                "id": v["id"], "x": v["x"], "y": v["y"], "kind": v["kind"],
                "line": v.get("line"),
                "stopped": v.get("stopped", False),
                "stopped_at_station": v.get("stopped_at_station", False)
            } for v in buses)
            MAX_CARS_CAP = 220 if target_vph < 1200 else (320 if target_vph < 1800 else 500)
            max_cars = max(0, MAX_CARS_CAP - len(render))
            if len(cars) > max_cars and max_cars > 0:
                step = max(1, len(cars) // max_cars)
                for i, v in enumerate(cars):
                    if i % step == 0:
                        render.append({"id": v["id"], "x": v["x"], "y": v["y"],
                                       "kind": v["kind"], "stopped": v.get("stopped", False)})
            else:
                render.extend({"id": v["id"], "x": v["x"], "y": v["y"],
                               "kind": v["kind"], "stopped": v.get("stopped", False)} for v in cars)

            frames.append({"t": t, "signals": signals, "vehicles": render})

        # ===== KPI =====
        
        estimated_vph = int(round(car_exited * 3600.0 / max(1, STEPS)))
        avg_headway = (float(np.mean(np.diff(car_exit_ts))) if len(car_exit_ts) >= 2 else None)
        kpis = {
            "mode": req.mode,
            "frames": len(frames),
            # 走廊汽車績效（純信號影響，因為模型無車跟車阻滯）
            "estimated_vph": estimated_vph,
            "avg_discharge_headway_s": (round(avg_headway, 2) if avg_headway is not None else None),
            "progression_rate": round(car_zero_stop / max(1, car_exited), 4),  # 零停車率
            "avg_stops_main": round(car_stops_sum / max(1, car_exited), 3),
            "avg_delay_main": round(car_delay_sum / max(1, car_exited), 2),     # 每車平均信號延滯(秒)
            "avg_travel_time_s": round(car_travel_sum / max(1, car_exited), 2), # 走廊旅行時間(秒)
            "target_vph": int(target_vph),
            "total_arrived": arrived,
            "target_vph": int(target_vph),
            "total_arrived": arrived,
        }

        # ===== 2-6 監控：計算各線觀測頭距/準點率 =====
        for lid, stats in monitor["lines"].items():
            ts = stats["arr_times"]
            if len(ts) >= 2:
                diffs = [ts[i] - ts[i-1] for i in range(1, len(ts))]
                avg = sum(diffs) / len(diffs)
                var = sum((d - avg) ** 2 for d in diffs) / len(diffs)
                stats["observed_headway_avg"] = round(avg, 1)
                stats["observed_headway_std"] = round(var ** 0.5, 1)
                tol = req.ab_tolerance_sec
                target = stats["scheduled_headway_sec"]
                stats["on_time_pct"] = round(100.0 * sum(1 for d in diffs if abs(d - target) <= tol) / len(diffs), 1)
            else:
                stats["observed_headway_avg"] = None
                stats["observed_headway_std"] = None
                stats["on_time_pct"] = None
            stats.pop("arr_times", None)

        # ===== 回傳 =====
        return {
            "session_id": session_id,
            "frames": frames,
            "kpis": kpis,
            "events": events,
            "monitor": monitor,   # ★ 前端可顯示監控卡片
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    # 改成 8000，和前端 API_BASE 一致
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True, log_config=None, access_log=False )
