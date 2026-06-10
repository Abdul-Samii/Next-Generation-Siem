import pandas as pd
import json
import time
from kafka import KafkaProducer
from datetime import datetime, timezone

print("=== V2X Vehicle Simulation — VeReMi Replay ===")

df = pd.read_csv('/home/kali/its-siem/datasets/balanced_veremi_dataset.csv')

print(f"Dataset loaded: {len(df)} messages")
print(f"Columns: {df.columns.tolist()}")

# Take balanced sample
df_benign = df[df['AttackerType'] == 'Benign'].sample(n=1000, random_state=42)
df_attack = df[df['AttackerType'] != 'Benign'].sample(n=1000, random_state=42)
df_sim    = pd.concat([df_benign, df_attack])
df_sim    = df_sim.sample(frac=1, random_state=42).reset_index(drop=True)

print(f"Simulation sample: {len(df_sim)} messages")
print(f"Benign:  {(df_sim['AttackerType']=='Benign').sum()}")
print(f"Attack:  {(df_sim['AttackerType']!='Benign').sum()}")

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)
print("Kafka connected\nStarting simulation...\n")

sent = attack = benign = 0

for idx, row in df_sim.iterrows():
    # Send ALL columns as-is — AttackerType kept for Kibana ground truth
    bsm = row.to_dict()
    bsm['source']     = "VeReMi-vehicle"
    bsm['@timestamp'] = datetime.now(timezone.utc).isoformat()

    producer.send('v2x-bsm', bsm)
    sent += 1

    if row['AttackerType'] == 'Benign':
        benign += 1
    else:
        attack += 1

    if sent % 100 == 0:
        print(f"Sent: {sent:4d} | Benign: {benign:3d} | "
              f"Attacks: {attack:3d} | Last: {row['AttackerType']}")

    time.sleep(0.1)

producer.flush()
print(f"\nTotal sent: {sent} | Benign: {benign} | Attacks: {attack}")
