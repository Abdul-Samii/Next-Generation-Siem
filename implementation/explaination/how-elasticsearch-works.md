# How Elasticsearch Works in This Project

## What it does

Elasticsearch stores every scored BSM event from the terminal pipeline so you can search through it, filter by attack type, and build dashboards in Kibana.

it is like a database of SIEM.

---

## How data gets there

The flow is:

```
attack_injector.py  →  Kafka (v2x-bsm topic)  →  ml_scorer.py  →  Elasticsearch
```

1. `attack_injector.py` reads rows from the VeReMi dataset and sends them to a Kafka topic called `v2x-bsm`
2. `ml_scorer.py` listens on that topic, runs each message through the ML models, and then writes the result to Elasticsearch
3. Elasticsearch stores it in a daily index called `v2x-scored-YYYY.MM.DD`

---

## Where it lives

Elasticsearch runs as a Docker container on port 9200. You can hit it directly in the browser or via curl:

```
http://localhost:9200
```

To see your indexed data:

```
http://localhost:9200/v2x-scored-*/_search?pretty
```

---

## Kibana

Kibana is the visual interface for Elasticsearch. It runs on port 5601:

```
http://localhost:5601
```

To query your data in Kibana:
1. Go to **Discover**
2. Select the `v2x-scored-*` data view
3. You can filter by `ml_attack_type`, `ml_is_attack`, `ml_severity` and so on

---

## Starting the stack

Everything runs through Docker Compose. From the `its-siem` folder:

```bash
docker compose up -d
```

This starts Elasticsearch, Kibana, Kafka, and Zookeeper together. Wait about 30 seconds for Elasticsearch to fully boot before running the scorer.

---

## Note on the web simulator

The web simulation does not use Elasticsearch at all. It scores data in memory and sends results directly to the browser over WebSocket. Nothing from the web simulator is stored or visible in Kibana.
