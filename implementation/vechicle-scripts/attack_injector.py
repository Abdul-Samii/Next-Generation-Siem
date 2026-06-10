#!/usr/bin/env python3
"""Replay rows from the VeReMi dataset into the v2x-bsm Kafka topic."""

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

# base rcvTime in dataset range so the scaler sees expected values
_RCV_BASE   = 30000.0
_rcv_offset = 0.0

from kafka import KafkaProducer

KAFKA_BROKER = 'localhost:9092'
KAFKA_TOPIC  = 'v2x-bsm'
DEFAULT_CSV  = Path('datasets/balanced_veremi_dataset.csv')

DOS_TYPES = {
    'DoS', 'DoSRandom', 'DoSDisruptive', 'Disruptive',
    'DoSRandomSybil', 'DoSDisruptiveSybil', 'DataReplaySybil', 'GridSybil',
}

FLOAT_FIELDS = [
    'rcvTime',
    'pos_0', 'pos_1', 'pos_noise_0', 'pos_noise_1',
    'spd_0', 'spd_1', 'spd_noise_0', 'spd_noise_1',
    'acl_0', 'acl_1', 'acl_noise_0', 'acl_noise_1',
    'hed_0', 'hed_1', 'hed_noise_0', 'hed_noise_1',
]
WINDOW_SIZE = 10


def load_rows(csv_path: Path, attack: str, count: int) -> list[dict]:
    # Benign rows each have a unique ReceiverID (1 row per receiver), so grouping
    # by ReceiverID would yield only 1 row. Collect across all receivers instead.
    if attack == 'Benign':
        rows = []
        with open(csv_path, newline='') as f:
            for row in csv.DictReader(f):
                if row['AttackerType'] == 'Benign':
                    rows.append(row)
                    if len(rows) >= count + WINDOW_SIZE:
                        break
        if not rows:
            raise SystemExit(f"No rows found for AttackerType='Benign' in {csv_path}")
        return rows

    groups: dict[str, list] = {}
    with open(csv_path, newline='') as f:
        for row in csv.DictReader(f):
            if row['AttackerType'] == attack:
                groups.setdefault(row['ReceiverID'], []).append(row)
    if not groups:
        raise SystemExit(f"No rows found for AttackerType='{attack}' in {csv_path}")
    # pick the receiver with the most messages so we always have a full sequence
    best = max(groups, key=lambda k: len(groups[k]))
    rows = sorted(groups[best], key=lambda r: float(r['rcvTime']))
    # return WINDOW_SIZE extra rows at the front for warm-up
    return rows[:count + WINDOW_SIZE]


def to_bsm(row: dict, vehicle_id: str, delay: float, synthetic_time: bool = False) -> dict:
    global _rcv_offset
    bsm = {k: float(row[k]) for k in FLOAT_FIELDS}
    if synthetic_time:
        # DoS only: tiny rcvTime gaps → huge msg_rate in scorer
        bsm['rcvTime'] = _RCV_BASE + _rcv_offset
        _rcv_offset   += max(delay, 0.001)
    # else: keep original dataset rcvTime so dist_error/delta_time stay correct
    bsm['ReceiverID']   = row['ReceiverID']
    bsm['AttackerType'] = row['AttackerType']
    bsm['is_attack']    = 0 if row['AttackerType'] == 'Benign' else 1
    bsm['source']       = 'veremi-injector'
    bsm['@timestamp']   = datetime.now(timezone.utc).isoformat()
    return bsm


TYPE_TO_GROUP = {
    'Benign':              'Benign',
    'ConstPos':            'PositionAttack',
    'ConstPosOffset':      'PositionAttack',
    'RandomPos':           'PositionAttack',
    'RandomPosOffset':     'PositionAttack',
    'ConstSpeed':          'SpeedManip',
    'ConstSpeedOffset':    'SpeedManip',
    'RandomSpeed':         'SpeedManip',
    'RandomSpeedOffset':   'SpeedManip',
    'DataReplay':          'ReplayAttack',
    'DelayedMessages':     'DelayedMessages',
    'EventualStop':        'EventualStop',
    'DoS':                 'DoSFamily',
    'DoSRandom':           'DoSFamily',
    'DoSDisruptive':       'DoSFamily',
    'Disruptive':          'DoSFamily',
    'DoSRandomSybil':      'DoSFamily',
    'DoSDisruptiveSybil':  'DoSFamily',
    'DataReplaySybil':     'DoSFamily',
    'GridSybil':           'DoSFamily',
}

GROUP_COLORS = {
    'DoSFamily':       '\033[91m',  # red
    'PositionAttack':  '\033[93m',  # yellow
    'SpeedManip':      '\033[95m',  # magenta
    'ReplayAttack':    '\033[96m',  # cyan
    'DelayedMessages': '\033[94m',  # blue
    'EventualStop':    '\033[33m',  # dark yellow
    'Benign':          '\033[92m',  # green
}
RESET = '\033[0m'


def pick_attack(csv_path: Path) -> str:
    print('Reading available attack types...')
    types: set[str] = set()
    with open(csv_path, newline='') as f:
        for row in csv.DictReader(f):
            types.add(row['AttackerType'])
            if len(types) >= 25:
                break
    group_order = ['DoSFamily', 'PositionAttack', 'SpeedManip',
                   'ReplayAttack', 'DelayedMessages', 'EventualStop', 'Benign']

    # group and sort within each group alphabetically
    grouped: dict[str, list] = {g: [] for g in group_order}
    for k in sorted(types):
        group = TYPE_TO_GROUP.get(k, 'Unknown')
        grouped.setdefault(group, []).append(k)

    # build ordered keys list matching display order so numbers are sequential
    ordered_keys: list[str] = []
    for group in group_order:
        ordered_keys.extend(grouped.get(group, []))

    print('\nAvailable attack types:\n')
    counter = 1
    for group in group_order:
        members = grouped.get(group, [])
        if not members:
            continue
        color = GROUP_COLORS.get(group, '')
        print(f'  {color}{group}{RESET}')
        for k in members:
            print(f'    [{counter:>2}]  {k}')
            counter += 1
        print()

    while True:
        raw = input('Select number: ').strip()
        if raw.isdigit() and 1 <= int(raw) <= len(ordered_keys):
            return ordered_keys[int(raw) - 1]
        print('      Invalid — try again.')


def main():
    parser = argparse.ArgumentParser(description='Replay VeReMi rows into Kafka')
    parser.add_argument('--attack', '-a', metavar='TYPE',
                        help='Attack type (omit for interactive menu)')
    parser.add_argument('--count', '-n', type=int, default=200,
                        help='Number of messages to send (default: 200)')
    parser.add_argument('--delay', '-d', type=float, default=0.0,
                        help='Seconds between messages (default: 0 — flood mode)')
    parser.add_argument('--vehicle-id', default='Attacker_1',
                        help='ReceiverID to stamp on each BSM (default: Attacker_1)')
    parser.add_argument('--csv', default=str(DEFAULT_CSV), metavar='PATH',
                        help=f'Path to VeReMi CSV (default: {DEFAULT_CSV})')
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f'CSV not found: {csv_path}')

    attack = args.attack or pick_attack(csv_path)

    is_dos = attack in DOS_TYPES
    # auto-tune count and delay unless user explicitly passed them
    if is_dos and args.count == 200 and args.delay == 0.0:
        count = 200
        delay = 0.0
    elif not is_dos and args.count == 200 and args.delay == 0.0:
        # 80 total: 30 silent warm-up + 50 displayed; no delay needed (rcvTime from dataset)
        count = 80
        delay = 0.0
    else:
        count = args.count
        delay = args.delay

    RED   = '\033[91m'
    GREEN = '\033[92m'
    RESET = '\033[0m'
    color = GREEN if attack == 'Benign' else RED
    label = 'benign' if attack == 'Benign' else 'ATTACK'

    print(f'\n  Attack  : {color}{attack}{RESET}')
    print(f'  Count   : {count}')
    print(f'  Delay   : {delay}s')
    print(f'  CSV     : {csv_path.name}\n')

    print(f"  {'#':<6}  {'RESULT':<8}  {'TYPE':<22}  {'pos_0':>10}  {'pos_1':>10}  {'spd_0':>8}")
    print('  ' + '─' * 70)

    display = 50
    rows = load_rows(csv_path, attack, count)
    # first (count - display) rows warm up the window silently; last 50 are shown
    warmup_rows  = rows[:count - display]
    display_rows = rows[count - display:]

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKER,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    print(f'  [warming up — sending {len(warmup_rows)} messages silently...]')
    for row in warmup_rows:
        producer.send(KAFKA_TOPIC, to_bsm(row, args.vehicle_id, delay, is_dos))
        if delay > 0:
            time.sleep(delay)
    producer.flush()
    print(f'  [window hot — showing last {display} messages]\n')

    for i, row in enumerate(display_rows, 1):
        bsm = to_bsm(row, args.vehicle_id, delay, is_dos)
        producer.send(KAFKA_TOPIC, bsm)
        print(f"  {i:<6}  {color}{label:<8}{RESET}  {attack:<22}  "
              f"{bsm['pos_0']:>10.2f}  {bsm['pos_1']:>10.2f}  {bsm['spd_0']:>8.3f}")
        if delay > 0:
            time.sleep(delay)

    producer.flush()
    producer.close()
    print(f'\n  Done — {count} rows sent.')


if __name__ == '__main__':
    main()
