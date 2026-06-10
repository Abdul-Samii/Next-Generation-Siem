# Using the SIEM Scripts

These scripts run on the Kali Linux machine. They work together, one injects attack traffic into Kafka and the other scores it with ML and sends results to Elasticsearch.

---

## Before you start

The Docker stack needs to be running first. From the `its-siem` folder:

```bash
docker compose up -d
```

Wait about 30 seconds for Elasticsearch to fully boot. You can check it's ready with:

(sometimes the kafka fails so you need to stop the containers and restart them all again)

```bash
curl http://localhost:9200
```

If you get a JSON response back, you're good to go.

---

## Script 1 — attack_injector.py

This script reads rows from the VeReMi dataset and sends them into Kafka. You run this to simulate an attacking vehicle broadcasting fake BSMs.

**Basic usage — interactive menu:**

```bash
cd vechicle-scripts
python3 attack_injector.py
```

It shows you a numbered list of all attack types grouped by category. Just type the number and press enter.

The script shows you a live table of what's being sent — pos_0, pos_1, spd_0 — so you can see the fake data as it goes out.

---

## Script 2 — ml_scorer.py

This script listens on the Kafka topic and scores every message that comes in. Run this in a separate terminal while the injector is sending data.

```bash
cd vechicle-scripts
python3 ml_scorer.py
```

It connects to Kafka and Elasticsearch automatically and stays running. Every message that comes through gets scored by the ML models and the result is printed to the terminal and written to Elasticsearch.

The output looks like this:

```
  ID                      RESULT    ATTACK TYPE           CONF
  ────────────────────────────────────────────────────────────
  Attacker_1              ATTACK    PositionAttack        0.9821
  Attacker_1              ATTACK    PositionAttack        0.9734
```

Once results are in Elasticsearch you can see them in Kibana at `http://localhost:5601` under the `v2x-scored-*` data view.

---

## Typical workflow

1. Start Docker stack — `docker compose up -d`
2. Open terminal 1 — run `ml_scorer.py` and leave it running
3. Open terminal 2 — run `attack_injector.py` and pick an attack
4. Watch the scorer terminal to see detections come in live
5. Open Kibana to explore the stored results

---

## Attack types available

| Group | Types |
|---|---|
| DoSFamily | DoS, DoSRandom, DoSDisruptive, Disruptive, DoSRandomSybil, DoSDisruptiveSybil, DataReplaySybil, GridSybil |
| PositionAttack | ConstPos, ConstPosOffset, RandomPos, RandomPosOffset |
| SpeedManip | ConstSpeed, ConstSpeedOffset, RandomSpeed, RandomSpeedOffset |
| ReplayAttack | DataReplay |
| DelayedMessages | DelayedMessages |
| EventualStop | EventualStop |
| Benign | Benign |

Benign means noremal traffic without attack.