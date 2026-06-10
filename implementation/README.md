# V2X Anomaly Detection System

Real-time ML-powered intrusion detection for Vehicle-to-Everything (V2X) communications, trained on the VeReMi dataset.

## Overview

Detects malicious BSM (Basic Safety Message) transmissions using a two-stage ML pipeline:

1. **XGBoost binary classifier** — attack vs. benign (≈100% accuracy)
2. **LightGBM multiclass classifier** — identifies attack group (68.85% accuracy across 6 classes)

**Attack groups detected:** DoSFamily · PositionAttack · SpeedManip · ReplayAttack · DelayedMessages · EventualStop

---

## Project Structure

```
├── simulation/                  # Real-time web simulator
│   ├── backend/                 # FastAPI + WebSocket server
│   │   ├── main.py
│   │   ├── simulator.py
│   │   └── scorer.py
│   └── frontend/                # React dashboard
├── vechicle-scripts/            # Terminal Kafka pipeline
│   ├── attack_injector.py       # Replay VeReMi rows into Kafka
│   ├── ml_scorer.py             # Kafka consumer + ML scoring → Elasticsearch
│   └── vehicle_simulation.py
├── balanced_veremi_dataset.csv  # VeReMi training/test dataset
├── model_binary.pkl             # XGBoost binary model
├── model_multiclass.pkl         # LightGBM multiclass model
└── scaler_binary.pkl / scaler_multi.pkl
```

---

## Components

### 1. Web Simulator

A browser-based real-time simulation with 9 vehicles on a city map. Vehicles can be set to normal, attack-only, or mixed mode. Detections are shown live on the map and in an event feed.

**Stack:** FastAPI · WebSocket · React · VeReMi dataset rows

```bash
# Backend
cd simulation/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd simulation/frontend
npm install
npm run dev
```

Open `http://localhost:5173`

### 2. Terminal Kafka Pipeline (SIEM)

Replays VeReMi dataset rows into Kafka, scores them with ML models, and indexes results into Elasticsearch for Kibana dashboards.

**Stack:** Kafka · Zookeeper · Elasticsearch 8.11 · Kibana 8.11 · Logstash

```bash
# Start SIEM stack (in its-siem/)
docker compose up -d

# Inject attack traffic
cd vechicle-scripts
python attack_injector.py

# Start ML scorer (separate terminal)
python ml_scorer.py
```

---

## Dataset

[VeReMi Extension Dataset](https://vehicularlab.net/veremi-extension/) — simulated V2X BSM traces with labeled attack scenarios across 17 features per message (position, speed, acceleration, heading + noise fields).

The `balanced_veremi_dataset.csv` used here is a preprocessed balanced sample.

---

## ML Features

| Feature set | Count | Used by |
|---|---|---|
| Raw (rcvTime, pos, spd, acl, hed + noise) | 17 | Binary + Multiclass |
| Delta (Δtime, Δpos, Δspd, dist\_error) | 10 | Multiclass |
| Window (pos\_std, spd\_std, hed\_std, msg\_rate) | 4 | Multiclass |

---

## Requirements

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose (for SIEM stack)
