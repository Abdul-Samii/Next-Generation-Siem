import os
import joblib
import pandas as pd
import numpy as np
from pathlib import Path
from collections import deque

MODEL_DIR = Path(os.environ.get("MODEL_PATH", Path(__file__).resolve().parent.parent.parent))

RAW_FEATURES = [
    "rcvTime",
    "pos_0", "pos_1",
    "pos_noise_0", "pos_noise_1",
    "spd_0", "spd_1",
    "spd_noise_0", "spd_noise_1",
    "acl_0", "acl_1",
    "acl_noise_0", "acl_noise_1",
    "hed_0", "hed_1",
    "hed_noise_0", "hed_noise_1",
]
DELTA_FEATURES = [
    "delta_time", "delta_pos_0", "delta_pos_1",
    "delta_spd_0", "delta_hed_0", "delta_dist",
    "expected_dist", "dist_error",
    "delta_pos_noise_0", "delta_pos_noise_1",
]
WINDOW_FEATURES = ["pos_std", "spd_std", "hed_std", "msg_rate"]
MULTI_FEATURES  = RAW_FEATURES + DELTA_FEATURES + WINDOW_FEATURES
WINDOW_SIZE     = 10

SEVERITY_MAP = {
    "DoSFamily":       "CRITICAL",
    "PositionAttack":  "HIGH",
    "ReplayAttack":    "HIGH",
    "SpeedManip":      "MEDIUM",
    "DelayedMessages": "MEDIUM",
    "EventualStop":    "LOW",
}


class Scorer:
    def __init__(self):
        self.ready = False
        self.receiver_state: dict[str, deque] = {}
        try:
            self.model_binary   = joblib.load(MODEL_DIR / "model_binary.pkl")
            self.model_multi    = joblib.load(MODEL_DIR / "model_multiclass.pkl")
            self.scaler_binary  = joblib.load(MODEL_DIR / "scaler_binary.pkl")
            self.scaler_multi   = joblib.load(MODEL_DIR / "scaler_multi.pkl")
            self.le_multi       = joblib.load(MODEL_DIR / "label_encoder_multi.pkl")
            self.ready = True
            print("✓ ML models loaded")
        except Exception as e:
            print(f"⚠ Models not loaded ({e}) — using heuristic scoring")

    def _std(self, vals):
        n = len(vals)
        if n < 2:
            return 0.0
        mu = sum(vals) / n
        return (sum((v - mu) ** 2 for v in vals) / n) ** 0.5

    def score(self, bsm: dict) -> dict:
        rid = str(bsm.get("receiver_id", "V-00"))
        if rid not in self.receiver_state:
            self.receiver_state[rid] = deque(maxlen=WINDOW_SIZE)

        raw = {f: float(bsm.get(f, 0.0)) for f in RAW_FEATURES}
        history = self.receiver_state[rid]
        prev = history[-1] if history else None
        history.append(raw)

        if not self.ready:
            return self._heuristic(bsm)

        # ── binary ──────────────────────────────────────────────────────
        binary_df     = pd.DataFrame([raw])
        binary_scaled = self.scaler_binary.transform(binary_df)
        binary_pred   = int(self.model_binary.predict(binary_scaled)[0])
        binary_conf   = float(self.model_binary.predict_proba(binary_scaled)[0].max())

        attack_label = "Benign"
        if binary_pred == 1:
            if prev is None:
                attack_label = "UnknownAttack"
            else:
                delta  = self._compute_delta(prev, raw)
                window = self._compute_window(history)
                multi_vec = [raw[f] for f in RAW_FEATURES] + delta + window
                multi_df  = pd.DataFrame([multi_vec], columns=MULTI_FEATURES)
                multi_sc  = pd.DataFrame(
                    self.scaler_multi.transform(multi_df), columns=MULTI_FEATURES
                )
                mp           = int(self.model_multi.predict(multi_sc)[0])
                attack_label = self.le_multi.inverse_transform([mp])[0]

        severity = "NONE" if binary_pred == 0 else SEVERITY_MAP.get(attack_label, "MEDIUM")
        return {
            "is_attack":   binary_pred,
            "attack_type": attack_label,
            "confidence":  round(binary_conf, 4),
            "severity":    severity,
        }

    def _compute_delta(self, prev, curr):
        dt   = curr["rcvTime"] - prev["rcvTime"]
        dp0  = curr["pos_0"]   - prev["pos_0"]
        dp1  = curr["pos_1"]   - prev["pos_1"]
        ds0  = curr["spd_0"]   - prev["spd_0"]
        dh0  = curr["hed_0"]   - prev["hed_0"]
        dist = (dp0 ** 2 + dp1 ** 2) ** 0.5
        exp  = abs(curr["spd_0"]) * abs(dt)
        return [dt, dp0, dp1, ds0, dh0, dist, exp, dist - exp,
                curr["pos_noise_0"] - prev["pos_noise_0"],
                curr["pos_noise_1"] - prev["pos_noise_1"]]

    def _compute_window(self, history):
        n = len(history)
        if n < 2:
            return [0.0] * 4
        pos  = [r["pos_0"]   for r in history]
        spd  = [r["spd_0"]   for r in history]
        hed  = [r["hed_0"]   for r in history]
        times = [r["rcvTime"] for r in history]
        span = times[-1] - times[0]
        return [self._std(pos), self._std(spd), self._std(hed), n / (span + 1e-9)]

    def _heuristic(self, bsm: dict) -> dict:
        attack_type = bsm.get("attack_type", "Benign")
        is_attack   = 0 if attack_type == "Benign" else 1
        group_map   = {
            "DoS": "DoSFamily", "DoSRandom": "DoSFamily", "DoSDisruptive": "DoSFamily",
            "Disruptive": "DoSFamily", "DoSRandomSybil": "DoSFamily",
            "DoSDisruptiveSybil": "DoSFamily", "DataReplaySybil": "DoSFamily",
            "GridSybil": "DoSFamily",
            "ConstPos": "PositionAttack", "ConstPosOffset": "PositionAttack",
            "RandomPos": "PositionAttack", "RandomPosOffset": "PositionAttack",
            "ConstSpeed": "SpeedManip", "ConstSpeedOffset": "SpeedManip",
            "RandomSpeed": "SpeedManip", "RandomSpeedOffset": "SpeedManip",
            "DataReplay": "ReplayAttack", "DelayedMessages": "DelayedMessages",
            "EventualStop": "EventualStop",
        }
        label    = group_map.get(attack_type, "Benign") if is_attack else "Benign"
        severity = "NONE" if not is_attack else SEVERITY_MAP.get(label, "MEDIUM")
        return {"is_attack": is_attack, "attack_type": label,
                "confidence": 0.99 if is_attack else 0.95, "severity": severity}
