import traci
import time
import json
import math
from kafka import KafkaProducer
from datetime import datetime, timezone

print('=== V2X SUMO Simulation → Kafka Pipeline ===')

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)
print('Connected to Kafka')

sumo_cmd = ['sumo-gui',
            '--configuration-file',
            '/home/kali/veins-veins-5.2/examples/veins/erlangen.sumo.cfg',
            '--step-length', '0.1']

traci.start(sumo_cmd)
print('SUMO started')

net_boundary = traci.simulation.getNetBoundary()
origin_x = net_boundary[0][0]
origin_y = net_boundary[0][1]
print(f'Simulation origin: ({origin_x:.1f}, {origin_y:.1f})')
print('Sending BSMs to Kafka...\n')

step = 0
total_sent = 0

try:
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        vehicles = traci.vehicle.getIDList()

        for veh_id in vehicles:
            pos = traci.vehicle.getPosition(veh_id)
            speed = traci.vehicle.getSpeed(veh_id)
            angle = traci.vehicle.getAngle(veh_id)
            accel = traci.vehicle.getAcceleration(veh_id)

            angle_rad = math.radians(angle)
            spd_0 = speed * math.sin(angle_rad)
            spd_1 = speed * math.cos(angle_rad)
            hed_0 = math.cos(angle_rad)
            hed_1 = math.sin(angle_rad)
            pos_0 = pos[0] - origin_x
            pos_1 = pos[1] - origin_y

            bsm = {
                'rcvTime':      traci.simulation.getTime(),
                'pos_0':        round(pos_0, 6),
                'pos_1':        round(pos_1, 6),
                'pos_noise_0':  0.0,
                'pos_noise_1':  0.0,
                'spd_0':        round(spd_0, 4),
                'spd_1':        round(spd_1, 4),
                'spd_noise_0':  0.0,
                'spd_noise_1':  0.0,
                'acl_0':        round(accel, 4),
                'acl_1':        0.0,
                'acl_noise_0':  0.0,
                'acl_noise_1':  0.0,
                'hed_0':        round(hed_0, 4),
                'hed_1':        round(hed_1, 4),
                'hed_noise_0':  0.0,
                'hed_noise_1':  0.0,
                'ReceiverID':   str(veh_id),
                'AttackerType': 'Benign',
                'is_attack':    0,
                'source':       'SUMO-vehicle',
                'timestamp':    datetime.now(timezone.utc).isoformat()
            }

            producer.send('v2x-bsm', bsm)
            total_sent += 1

        if step % 50 == 0:
            print(f'Step {step:4d} | Vehicles: {len(vehicles):2d} | Total BSMs sent: {total_sent}')

        step += 1
        time.sleep(0.05)

except KeyboardInterrupt:
    print('\nSimulation stopped')

finally:
    producer.flush()
    traci.close()
    print(f'\nTotal BSMs sent: {total_sent}')
