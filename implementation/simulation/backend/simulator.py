import math
import random
import csv
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

CANVAS_W = 940
CANVAS_H = 620
SCALE    = 1.5        # canvas px → sim metres
SIM_BASE = 30000.0    # base rcvTime (within dataset scaler range)

# ── Road layout ──────────────────────────────────────────────────────────────
H_ROADS = [120, 310, 500]   # y positions of horizontal roads
V_ROADS = [160, 400, 700, 880]  # x positions of vertical roads  (last two off-screen edges used as entry/exit)

# Vehicle routes: list of (x, y) waypoints that loop
ROUTES = [
    # Horizontal roads  left → right → loop
    [(0, 120), (940, 120)],
    [(940, 120), (0, 120)],
    [(0, 310), (940, 310)],
    [(940, 310), (0, 310)],
    [(0, 500), (940, 500)],
    [(940, 500), (0, 500)],
    # Vertical roads  top → bottom → loop
    [(160, 0), (160, 620)],
    [(400, 620), (400, 0)],
    [(700, 0), (700, 620)],
]

VEHICLE_COLORS = {
    "benign":  "#22c55e",
    "attack":  "#ef4444",
    "unknown": "#f59e0b",
}

DOS_TYPES = {
    "DoS", "DoSRandom", "DoSDisruptive", "Disruptive",
    "DoSRandomSybil", "DoSDisruptiveSybil", "DataReplaySybil", "GridSybil",
}

ATTACK_LIMIT = {
    "dos":   200,   # flood mode
    "other":  80,   # 30 warm-up + 50 displayed
}

DATASET_PATH    = Path(__file__).resolve().parent.parent.parent / "balanced_veremi_dataset.csv"
BENIGN_POOL_SIZE = 600   # benign rows loaded at startup for synthetic BSMs


@dataclass
class Vehicle:
    id: str
    x: float
    y: float
    angle: float          # degrees
    speed: float          # px/sec
    route: list
    route_progress: float = 0.0   # 0.0–1.0 along current segment
    is_attack: bool = False
    attack_type: str = "Benign"
    ml_group: str = "Benign"
    severity: str = "NONE"
    confidence: float = 1.0
    pulse: float = 0.0    # 0–1, drives CSS pulse ring
    wave: float = 0.0     # 0–1, drives BSM radio wave animation
    attack_rows: list = field(default_factory=list)
    attack_row_idx: int = 0
    attack_limit: int = 0
    sim_time: float = SIM_BASE
    rcv_offset: float = 0.0
    benign_pool_idx: int = 0
    bsm_tick: int = 0        # ticks since last BSM was sent
    bsm_interval: int = 1    # ticks between BSMs (1=every tick, 5≈0.5s)
    warmup_remaining: int = 0  # BSMs still in silent warm-up phase


class Simulator:
    TICK_DT = 0.1   # seconds per simulation tick

    def __init__(self, scorer):
        self.scorer          = scorer
        self.running         = False
        self.mode            = "mixed"
        self._benign_pool    = self._load_benign_pool()
        self.vehicles        = self._init_vehicles()
        self.sim_time        = SIM_BASE
        self._attack_cache: dict[str, list] = {}
        self._pending_attack = None
        self._last_attack    = None

    # ── public API ────────────────────────────────────────────────────────
    def start(self, mode: str = "mixed", attack_type: str = None):
        self.clear_attacks()
        self.scorer.receiver_state.clear()   # flush temporal history so stale features don't carry over
        self.running = True
        self.mode    = mode
        if mode == "attack" and attack_type:
            self._pending_attack = attack_type
        else:
            self._pending_attack = None
            # Benign vehicles are never armed via _inject_all, so unblock their scoring now
            for v in self.vehicles:
                v.bsm_interval = 5

    def stop(self):
        self.running = False
        self.mode    = "mixed"
        self.clear_attacks()

    def inject_attack(self, attack_type: str):
        """Inject into one random benign vehicle (used for mixed-mode manual injection)."""
        rows = self._load_attack_rows(attack_type)
        if not rows:
            return
        self._last_attack = attack_type
        limit = ATTACK_LIMIT["dos"] if attack_type in DOS_TYPES else ATTACK_LIMIT["other"]
        candidates = [v for v in self.vehicles if not v.is_attack]
        if not candidates:
            candidates = self.vehicles
        victim = random.choice(candidates)
        self._arm_vehicle(victim, attack_type, rows, limit, offset=0)

    def _inject_all(self, attack_type: str):
        """Inject into ALL vehicles (used for attack-only mode)."""
        rows = self._load_attack_rows(attack_type)
        if not rows:
            return
        self._last_attack = attack_type
        limit = ATTACK_LIMIT["dos"] if attack_type in DOS_TYPES else ATTACK_LIMIT["other"]
        step = max(1, len(rows) // len(self.vehicles))
        for i, v in enumerate(self.vehicles):
            self._arm_vehicle(v, attack_type, rows, limit, offset=i * step)

    def _arm_vehicle(self, v: "Vehicle", attack_type: str, rows: list, limit: int, offset: int):
        start = offset % max(1, len(rows))
        rotated = rows[start:] + rows[:start]
        v.is_attack      = True
        v.attack_type    = attack_type
        v.attack_rows    = rotated[:limit]
        v.attack_row_idx = 0
        v.attack_limit   = len(v.attack_rows)
        # rcv_offset accumulates across re-arm cycles — never reset here.
        # A reset causes rcvTime to jump backward, breaking the scorer's window span.
        v.bsm_tick        = 0
        v.warmup_remaining = 0   # no fast warm-up (it blocked the async loop)
        v.bsm_interval    = 1 if attack_type in DOS_TYPES else 5

    def clear_attacks(self):
        for v in self.vehicles:
            v.is_attack      = False
            v.attack_type    = "Benign"
            v.attack_rows    = []
            v.attack_row_idx = 0
            v.attack_limit   = 0
            v.ml_group       = "Benign"
            v.severity       = "NONE"
            v.pulse          = 0.0
            v.bsm_tick        = 0
            v.bsm_interval    = 999  # block scoring until vehicle is properly armed
            v.warmup_remaining = 0
            v.rcv_offset     = 0.0

    def tick(self) -> list[dict]:
        self.sim_time += self.TICK_DT
        events = []

        if self.mode == "attack" and self._pending_attack:
            self._inject_all(self._pending_attack)
            self._pending_attack = None

        for v in self.vehicles:
            self._move(v)
            v.wave = (v.wave + 0.15) % 1.0

            # In attack-only mode, re-arm each vehicle as soon as it finishes its burst
            if self.mode == "attack" and not v.is_attack and self._last_attack:
                rows  = self._load_attack_rows(self._last_attack)
                limit = ATTACK_LIMIT["dos" if self._last_attack in DOS_TYPES else "other"]
                self._arm_vehicle(v, self._last_attack, rows, limit,
                                  offset=random.randint(0, max(0, len(rows) - limit)))

            v.bsm_tick += 1
            bsm_scored = v.bsm_tick >= v.bsm_interval
            if bsm_scored:
                v.bsm_tick = 0
                bsm    = self._generate_bsm(v)
                result = self.scorer.score(bsm)
                v.ml_group   = result["attack_type"]
                v.severity   = result["severity"]
                v.confidence = result["confidence"]
                if result["is_attack"]:
                    v.pulse = min(v.pulse + 0.3, 1.0)
                    events.append({
                        "type":       "detection",
                        "vehicle_id": v.id,
                        "attack_type": result["attack_type"],
                        "severity":   result["severity"],
                        "confidence": result["confidence"],
                        "ts":         time.strftime("%H:%M:%S"),
                    })
                else:
                    v.pulse = max(v.pulse - 0.05, 0.0)

            events.append({
                "type":        "vehicle_update",
                "id":          v.id,
                "x":           round(v.x, 1),
                "y":           round(v.y, 1),
                "angle":       round(v.angle, 1),
                "is_attack":   v.ml_group != "Benign",
                "attack_type": v.ml_group,
                "severity":    v.severity,
                "confidence":  v.confidence,
                "pulse":       round(v.pulse, 2),
                "wave":        round(v.wave, 2),
                "bsm_scored":  bsm_scored,
            })

        return events

    def get_vehicle_states(self) -> list[dict]:
        return [
            {"id": v.id, "x": round(v.x, 1), "y": round(v.y, 1),
             "angle": round(v.angle, 1), "is_attack": v.is_attack,
             "attack_type": v.ml_group, "severity": v.severity,
             "confidence": v.confidence, "pulse": round(v.pulse, 2),
             "wave": round(v.wave, 2)}
            for v in self.vehicles
        ]

    # ── internals ─────────────────────────────────────────────────────────
    def _init_vehicles(self) -> list[Vehicle]:
        vehicles = []
        pool_len = max(1, len(self._benign_pool))
        for i, route in enumerate(ROUTES):
            progress = random.random()
            x, y, angle = self._position_on_route(route, progress)
            speed = random.uniform(70, 130)
            vehicles.append(Vehicle(
                id=f"V-{i+1:02d}",
                x=x, y=y, angle=angle,
                speed=speed,
                route=route,
                route_progress=progress,
                benign_pool_idx=(i * (pool_len // len(ROUTES))) % pool_len,
            ))
        return vehicles

    def _position_on_route(self, route, progress):
        p0, p1  = route[0], route[1]
        x = p0[0] + (p1[0] - p0[0]) * progress
        y = p0[1] + (p1[1] - p0[1]) * progress
        dx, dy  = p1[0] - p0[0], p1[1] - p0[1]
        angle   = math.degrees(math.atan2(dy, dx))
        return x, y, angle

    def _move(self, v: Vehicle):
        p0, p1   = v.route[0], v.route[1]
        seg_len  = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        step     = v.speed * self.TICK_DT
        v.route_progress += step / (seg_len + 1e-9)
        if v.route_progress >= 1.0:
            v.route_progress = 0.0
        v.x, v.y, v.angle = self._position_on_route(v.route, v.route_progress)

    def _generate_bsm(self, v: Vehicle) -> dict:
        if v.is_attack and v.attack_rows:
            if v.attack_row_idx >= v.attack_limit:
                if self.mode == "attack" and self._last_attack:
                    # Attack-only mode: re-arm immediately, never go benign
                    rows  = self._load_attack_rows(self._last_attack)
                    limit = ATTACK_LIMIT["dos" if self._last_attack in DOS_TYPES else "other"]
                    self._arm_vehicle(v, self._last_attack, rows, limit,
                                      offset=random.randint(0, max(0, len(rows) - limit)))
                else:
                    # Mixed/normal: vehicle returns to benign after burst
                    v.is_attack   = False
                    v.attack_type = "Benign"
                    v.attack_rows = []
                    v.pulse       = 0.0
                    return self._generate_bsm(v)
            row = v.attack_rows[v.attack_row_idx]
            v.attack_row_idx += 1
            is_dos = v.attack_type in DOS_TYPES
            # Synthetic rcvTime increments tuned to match training data msg_rate distribution:
            #   DoS  → +0.001 s → msg_rate ≈ 1000  (flood signal, clearly DoSFamily)
            #   else → +0.200 s → msg_rate ≈ 5.6   (matches training mean ≈ 4.7 msg/s)
            # +0.1 s was too fast (msg_rate≈11), pushing the multiclass model toward DoSFamily.
            v.rcv_offset += 0.001 if is_dos else 0.2
            rcv_time = SIM_BASE + v.rcv_offset
            bsm = {
                "receiver_id":  v.id,
                "rcvTime":      rcv_time,
                "pos_0":        float(row["pos_0"]),
                "pos_1":        float(row["pos_1"]),
                "pos_noise_0":  float(row["pos_noise_0"]),
                "pos_noise_1":  float(row["pos_noise_1"]),
                "spd_0":        float(row["spd_0"]),
                "spd_1":        float(row["spd_1"]),
                "spd_noise_0":  float(row["spd_noise_0"]),
                "spd_noise_1":  float(row["spd_noise_1"]),
                "acl_0":        float(row["acl_0"]),
                "acl_1":        float(row["acl_1"]),
                "acl_noise_0":  float(row["acl_noise_0"]),
                "acl_noise_1":  float(row["acl_noise_1"]),
                "hed_0":        float(row["hed_0"]),
                "hed_1":        float(row["hed_1"]),
                "hed_noise_0":  float(row["hed_noise_0"]),
                "hed_noise_1":  float(row["hed_noise_1"]),
                "attack_type":  v.attack_type,
            }
        else:
            # Pull from real benign pool — exact training distribution, no synthetic mismatch
            if self._benign_pool:
                row = self._benign_pool[v.benign_pool_idx % len(self._benign_pool)]
                v.benign_pool_idx += 1
                bsm = {
                    "receiver_id":  v.id,
                    "rcvTime":      self.sim_time,
                    "pos_0":        float(row["pos_0"]),
                    "pos_1":        float(row["pos_1"]),
                    "pos_noise_0":  float(row["pos_noise_0"]),
                    "pos_noise_1":  float(row["pos_noise_1"]),
                    "spd_0":        float(row["spd_0"]),
                    "spd_1":        float(row["spd_1"]),
                    "spd_noise_0":  float(row["spd_noise_0"]),
                    "spd_noise_1":  float(row["spd_noise_1"]),
                    "acl_0":        float(row["acl_0"]),
                    "acl_1":        float(row["acl_1"]),
                    "acl_noise_0":  float(row["acl_noise_0"]),
                    "acl_noise_1":  float(row["acl_noise_1"]),
                    "hed_0":        float(row["hed_0"]),
                    "hed_1":        float(row["hed_1"]),
                    "hed_noise_0":  float(row["hed_noise_0"]),
                    "hed_noise_1":  float(row["hed_noise_1"]),
                    "attack_type":  "Benign",
                }
            else:
                # fallback if dataset unavailable
                hed_deg = (v.angle + 90) % 360  # offset to ~180 range (benign distribution)
                spd_mag = random.uniform(8, 42)
                bsm = {
                    "receiver_id":  v.id,
                    "rcvTime":      self.sim_time,
                    "pos_0":        (v.x / CANVAS_W) * 200 - 100,
                    "pos_1":        (v.y / CANVAS_H) * 200 - 100,
                    "pos_noise_0":  random.uniform(-0.04, 0.04),
                    "pos_noise_1":  random.uniform(-0.04, 0.04),
                    "spd_0":        max(0.05, spd_mag + random.gauss(0, 2)),
                    "spd_1":        max(0.05, spd_mag + random.gauss(0, 2)),
                    "spd_noise_0":  random.uniform(-0.04, 0.04),
                    "spd_noise_1":  random.uniform(-0.04, 0.04),
                    "acl_0":        random.gauss(0, 1.5),
                    "acl_1":        random.gauss(0, 1.5),
                    "acl_noise_0":  random.uniform(-0.04, 0.04),
                    "acl_noise_1":  random.uniform(-0.04, 0.04),
                    "hed_0":        hed_deg,
                    "hed_1":        (hed_deg + random.gauss(0, 2)) % 360,
                    "hed_noise_0":  random.uniform(-0.04, 0.04),
                    "hed_noise_1":  random.uniform(-0.04, 0.04),
                    "attack_type":  "Benign",
                }
        return bsm

    def _load_benign_pool(self) -> list:
        if not DATASET_PATH.exists():
            return []
        rows = []
        with open(DATASET_PATH, newline="") as f:
            for row in csv.DictReader(f):
                if row["AttackerType"] == "Benign":
                    rows.append(row)
                    if len(rows) >= BENIGN_POOL_SIZE:
                        break
        random.shuffle(rows)
        print(f"✓ Benign pool loaded ({len(rows)} rows)")
        return rows

    def _load_attack_rows(self, attack_type: str) -> list:
        if attack_type in self._attack_cache:
            return self._attack_cache[attack_type]
        if not DATASET_PATH.exists():
            return []
        groups: dict[str, list] = {}
        with open(DATASET_PATH, newline="") as f:
            for row in csv.DictReader(f):
                if row["AttackerType"] == attack_type:
                    groups.setdefault(row["ReceiverID"], []).append(row)
        if not groups:
            return []
        best = max(groups, key=lambda k: len(groups[k]))
        rows = sorted(groups[best], key=lambda r: float(r["rcvTime"]))
        self._attack_cache[attack_type] = rows
        return rows
