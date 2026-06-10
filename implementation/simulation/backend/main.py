import asyncio
import json
from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState
from fastapi.middleware.cors import CORSMiddleware
from scorer import Scorer
from simulator import Simulator

app = FastAPI(title="V2X Simulation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

scorer    = Scorer()
simulator = Simulator(scorer)
clients: list[WebSocket] = []
stats = {"total": 0, "attacks": 0, "benign": 0, "by_type": {}}


async def broadcast(msg: dict):
    dead = []
    for ws in clients:
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(json.dumps(msg))
            else:
                dead.append(ws)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in clients:
            clients.remove(ws)


async def simulation_loop():
    while True:
        if simulator.running and clients:
            events = simulator.tick()
            detections = []
            vehicles   = []
            for e in events:
                if e["type"] == "detection":
                    detections.append(e)
                    stats["attacks"] += 1
                    stats["total"]   += 1
                    t = e["attack_type"]
                    stats["by_type"][t] = stats["by_type"].get(t, 0) + 1
                elif e["type"] == "vehicle_update":
                    # Only count benign stats when a BSM was actually scored this tick
                    if e.get("bsm_scored") and not e["is_attack"]:
                        stats["benign"] += 1
                        stats["total"]  += 1
                    vehicles.append(e)

            if vehicles:
                await broadcast({"type": "batch", "vehicles": vehicles,
                                 "detections": detections, "stats": dict(stats)})
        await asyncio.sleep(0.12)


@app.on_event("startup")
async def startup():
    asyncio.create_task(simulation_loop())


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    try:
        await ws.send_text(json.dumps({
            "type": "init",
            "vehicles": simulator.get_vehicle_states(),
            "running": simulator.running,
            "stats": dict(stats),
        }))
    except Exception:
        if ws in clients:
            clients.remove(ws)
        return

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            action = msg.get("action")

            if action == "start":
                mode        = msg.get("mode", "mixed")
                attack_type = msg.get("attack_type")
                stats.update({"total": 0, "attacks": 0, "benign": 0, "by_type": {}})
                simulator.start(mode=mode, attack_type=attack_type)
                await broadcast({"type": "status", "running": True, "stats": dict(stats)})

            elif action == "stop":
                simulator.stop()
                await broadcast({"type": "status", "running": False})

            elif action == "inject":
                simulator.inject_attack(msg["attack_type"])
                await broadcast({"type": "injected", "attack_type": msg["attack_type"]})

            elif action == "clear":
                simulator.clear_attacks()
                stats.update({"total": 0, "attacks": 0, "benign": 0, "by_type": {}})
                await broadcast({"type": "cleared"})

    except (WebSocketDisconnect, Exception):
        if ws in clients:
            clients.remove(ws)
