import json
import joblib
import os
import pandas as pd
import requests
from collections import deque
from kafka import KafkaConsumer
from datetime import datetime, timezone
from pathlib import Path

MODEL_DIR = Path(os.environ.get('MODEL_PATH', Path(__file__).resolve().parent / 'ai-models'))
MODEL_BINARY = MODEL_DIR / 'model_binary.pkl'
MODEL_MULTI = MODEL_DIR / 'model_multiclass.pkl'
SCALER_BINARY = MODEL_DIR / 'scaler_binary.pkl'
SCALER_MULTI = MODEL_DIR / 'scaler_multi.pkl'
LABEL_ENCODER_MULTI = MODEL_DIR / 'label_encoder_multi.pkl'
RECEIVER_ENCODER = MODEL_DIR / 'receiver_encoder.pkl'

KAFKA_BROKER = 'localhost:9092'
KAFKA_TOPIC = 'v2x-bsm'
KAFKA_GROUP = 'ml-scorer-v3'
ELASTICSEARCH_URL = 'http://localhost:9200'
OUTPUT_INDEX = 'v2x-scored'

RAW_FEATURES = [
    'rcvTime',
    'pos_0', 'pos_1',
    'pos_noise_0', 'pos_noise_1',
    'spd_0', 'spd_1',
    'spd_noise_0', 'spd_noise_1',
    'acl_0', 'acl_1',
    'acl_noise_0', 'acl_noise_1',
    'hed_0', 'hed_1',
    'hed_noise_0', 'hed_noise_1'
]
DELTA_FEATURES = [
    'delta_time',
    'delta_pos_0', 'delta_pos_1',
    'delta_spd_0',
    'delta_hed_0',
    'delta_dist',
    'expected_dist',
    'dist_error',
    'delta_pos_noise_0', 'delta_pos_noise_1'
]
WINDOW_SIZE = 10
WINDOW_FEATURES = ['pos_std', 'spd_std', 'hed_std', 'msg_rate']
MULTI_FEATURES = RAW_FEATURES + DELTA_FEATURES + WINDOW_FEATURES


def load_models():
    print('=== V2X ML Anomaly Detection Scorer ===')
    if not MODEL_BINARY.exists() or not MODEL_MULTI.exists():
        raise FileNotFoundError(f'Missing model files in {MODEL_DIR}')

    model_binary = joblib.load(MODEL_BINARY)
    model_multi = joblib.load(MODEL_MULTI)
    scaler_binary = joblib.load(SCALER_BINARY)
    scaler_multi = joblib.load(SCALER_MULTI)
    le_multi = joblib.load(LABEL_ENCODER_MULTI)
    receiver_encoder = None
    if RECEIVER_ENCODER.exists():
        receiver_encoder = joblib.load(RECEIVER_ENCODER)

    print('All models loaded')
    print(f'Model directory: {MODEL_DIR}')
    print(f'Binary features: {RAW_FEATURES}')
    print(f'Multiclass features: {MULTI_FEATURES}')
    return model_binary, model_multi, scaler_binary, scaler_multi, le_multi, receiver_encoder


def store_in_es(event):
    index = f'{OUTPUT_INDEX}-{datetime.now(timezone.utc).strftime("%Y.%m.%d")}'
    url = f'{ELASTICSEARCH_URL}/{index}/_doc'
    resp = requests.post(url, json=event, timeout=10)
    return resp.status_code


def ensure_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_raw_record(event):
    return {name: ensure_float(event.get(name, 0.0)) for name in RAW_FEATURES}


def compute_delta(prev, current):
    if prev is None:
        return [0.0] * len(DELTA_FEATURES), False

    delta_time = current['rcvTime'] - prev['rcvTime']
    delta_pos_0 = current['pos_0'] - prev['pos_0']
    delta_pos_1 = current['pos_1'] - prev['pos_1']
    delta_spd_0 = current['spd_0'] - prev['spd_0']
    delta_hed_0 = current['hed_0'] - prev['hed_0']
    delta_dist = (delta_pos_0**2 + delta_pos_1**2)**0.5
    expected_dist = abs(current['spd_0']) * abs(delta_time)
    dist_error = delta_dist - expected_dist
    delta_pos_noise_0 = current['pos_noise_0'] - prev['pos_noise_0']
    delta_pos_noise_1 = current['pos_noise_1'] - prev['pos_noise_1']

    return [
        delta_time,
        delta_pos_0, delta_pos_1,
        delta_spd_0,
        delta_hed_0,
        delta_dist,
        expected_dist,
        dist_error,
        delta_pos_noise_0, delta_pos_noise_1
    ], True


def compute_window_features(history: deque) -> list:
    n = len(history)
    if n < 2:
        return [0.0] * len(WINDOW_FEATURES)
    pos_vals = [r['pos_0']    for r in history]
    spd_vals = [r['spd_0']    for r in history]
    hed_vals = [r['hed_0']    for r in history]
    times    = [r['rcvTime']  for r in history]
    def std(vals):
        mu = sum(vals) / n
        return (sum((v - mu) ** 2 for v in vals) / n) ** 0.5
    span = times[-1] - times[0]
    msg_rate = n / (span + 1e-9)
    return [std(pos_vals), std(spd_vals), std(hed_vals), msg_rate]


def score_event(event, model_binary, model_multi, scaler_binary, scaler_multi, le_multi, receiver_state):
    raw = build_raw_record(event)
    binary_vector = [raw[name] for name in RAW_FEATURES]
    binary_df = pd.DataFrame([binary_vector], columns=RAW_FEATURES)
    binary_scaled = scaler_binary.transform(binary_df)

    binary_pred = int(model_binary.predict(binary_scaled)[0])
    binary_conf = float(model_binary.predict_proba(binary_scaled)[0].max())
    attack_label = 'Benign'

    receiver_id = str(event.get('ReceiverID', 'UNKNOWN'))
    if receiver_id not in receiver_state:
        receiver_state[receiver_id] = deque(maxlen=WINDOW_SIZE)
    history = receiver_state[receiver_id]
    prev_record = history[-1] if history else None
    history.append(raw)

    if binary_pred == 1:
        delta_vector, has_history = compute_delta(prev_record, raw)
        if has_history:
            window_vector = compute_window_features(history)
            multi_vector = binary_vector + delta_vector + window_vector
            multi_df = pd.DataFrame([multi_vector], columns=MULTI_FEATURES)
            multi_scaled = pd.DataFrame(scaler_multi.transform(multi_df), columns=MULTI_FEATURES)
            multi_pred = int(model_multi.predict(multi_scaled)[0])
            attack_label = le_multi.inverse_transform([multi_pred])[0]
        else:
            attack_label = 'UnknownAttack'

    event['ml_is_attack'] = binary_pred
    event['ml_confidence'] = round(binary_conf, 4)
    event['ml_attack_type'] = attack_label
    event['ml_scored_at'] = datetime.now(timezone.utc).isoformat()
    event['@timestamp'] = datetime.now(timezone.utc).isoformat()

    if binary_pred == 0:
        event['ml_severity'] = 'NONE'
    elif attack_label == 'DoSFamily':
        event['ml_severity'] = 'CRITICAL'
    elif attack_label in ('PositionAttack', 'ReplayAttack'):
        event['ml_severity'] = 'HIGH'
    elif attack_label in ('SpeedManip', 'DelayedMessages'):
        event['ml_severity'] = 'MEDIUM'
    elif attack_label == 'EventualStop':
        event['ml_severity'] = 'LOW'
    else:
        event['ml_severity'] = 'MEDIUM'

    return event, binary_pred, binary_conf, attack_label


def main():
    model_binary, model_multi, scaler_binary, scaler_multi, le_multi, receiver_encoder = load_models()
    receiver_state = {}

    try:
        resp = requests.get(ELASTICSEARCH_URL, timeout=5)
        print(f'Elasticsearch connected: {ELASTICSEARCH_URL}')
        print(f"Version: {resp.json()['version']['number']}")
    except Exception as e:
        print(f'ERROR: Cannot reach Elasticsearch: {e}')
        return

    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BROKER,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        group_id=KAFKA_GROUP,
        auto_offset_reset='latest'
    )
    print('Kafka consumer connected')
    print(f'Listening on topic: {KAFKA_TOPIC}\n')

    scored = attacks = benign = 0

    print(f"  {'ID':<22}  {'RESULT':<8}  {'ATTACK TYPE':<20}  {'CONF':>8}")
    print('  ' + '─' * 64)

    for message in consumer:
        event = message.value
        try:
            event, binary_pred, conf, attack_label = score_event(
                event, model_binary, model_multi, scaler_binary, scaler_multi, le_multi, receiver_state)

            event_id = event.get('VehicleID') or event.get('ReceiverID') or 'UNKNOWN'
            RED = '\033[91m'
            GREEN = '\033[92m'
            RESET = '\033[0m'
            color = RED if binary_pred == 1 else GREEN
            result_str = 'ATTACK' if binary_pred == 1 else 'benign'
            print(f"  {str(event_id):<22}  {color}{result_str:<8}{RESET}  {attack_label:<20}  {conf:>8.4f}")

            store_in_es(event)

            scored += 1
            if binary_pred == 1:
                attacks += 1
            else:
                benign += 1


        except Exception as e:
            print(f'Error: {e}')
            continue

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nScorer stopped')
        print(f'Total: {scored} | Benign: {benign} | Attacks: {attacks}')
        print(f'FPR: {attacks/scored:.4f}' if scored > 0 else '')
        print('Check Kibana: http://localhost:5601')
