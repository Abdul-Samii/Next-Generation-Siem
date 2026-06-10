from kafka import KafkaProducer
import json
import time
import math
from datetime import datetime, timezone

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

for i in range(5):
    angle_deg = 270.0 + i * 2.0
    angle_rad = math.radians(angle_deg)
    speed = 13.8
    spd_0 = speed * math.sin(angle_rad)
    spd_1 = speed * math.cos(angle_rad)
    hed_0 = math.cos(angle_rad)
    hed_1 = math.sin(angle_rad)

    bsm = {
        'rcvTime':       time.time(),
        'pos_0':         2.3522 + (i * 0.001),
        'pos_1':         48.8566 + (i * 0.001),
        'pos_noise_0':   0.0,
        'pos_noise_1':   0.0,
        'spd_0':         round(spd_0, 4),
        'spd_1':         round(spd_1, 4),
        'spd_noise_0':   0.0,
        'spd_noise_1':   0.0,
        'acl_0':         -0.26,
        'acl_1':         0.0,
        'acl_noise_0':   0.0,
        'acl_noise_1':   0.0,
        'hed_0':         round(hed_0, 4),
        'hed_1':         round(hed_1, 4),
        'hed_noise_0':   0.0,
        'hed_noise_1':   0.0,
        'ReceiverID':    f'vehicle-0{i+1}',
        'AttackerType':  'Benign',
        'is_attack':     0,
        'source':        'test-pipeline',
        'timestamp':     datetime.now(timezone.utc).isoformat()
    }

    producer.send('v2x-bsm', bsm)
    print(f'Sent BSM {i+1}')
    time.sleep(0.1)

producer.flush()
print('Done — check Kibana at http://localhost:5601')
