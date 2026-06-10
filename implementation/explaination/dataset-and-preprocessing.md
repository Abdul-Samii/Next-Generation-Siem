# Dataset and Preprocessing

This explains how the raw VeReMi data was cleaned, engineered, and prepared before training the models.

---

## The Raw Dataset

The dataset is `balanced_veremi_dataset.csv`. It has 2.27 million rows and 19 columns.

Each row is one BSM (Basic Safety Message) received by a vehicle. The columns are:

- **rcvTime** — timestamp when the message was received
- **pos_0, pos_1** — reported position (x, y)
- **spd_0, spd_1** — reported speed
- **acl_0, acl_1** — reported acceleration
- **hed_0, hed_1** — reported heading (degrees)
- **pos_noise_0/1, spd_noise_0/1, acl_noise_0/1, hed_noise_0/1** — sensor noise fields
- **ReceiverID** — which vehicle received this message
- **AttackerType** — the label (Benign, DoS, RandomPos, etc.)

There are 20 attack types plus Benign, each with exactly 113,477 rows.

---

## Step 1 — Encode the labels

**ReceiverID** is a string like `Receiver_138651`. It gets converted to a number using LabelEncoder so the model can use it. The encoder is saved as `receiver_encoder.pkl`.

Two label columns are created:

- **Y_binary** — 0 for Benign, 1 for everything else
- **Y_multi** — a number from 0 to 19 for each attack type (later regrouped)

---

## Step 2 — Engineer new features (attack-only)

The raw features alone are not enough to tell attack types apart. So we add two sets of engineered features, computed only on the attack rows.

**Delta features** — how much each value changed from the previous message for the same receiver:

- `delta_time` — time gap between messages
- `delta_pos_0, delta_pos_1` — how far the position jumped
- `delta_spd_0` — speed change
- `delta_hed_0` — heading change
- `delta_dist` — actual distance moved (from position)
- `expected_dist` — distance the vehicle *should* have moved based on speed × time
- `dist_error` — difference between actual and expected distance (large for position fakers)
- `delta_pos_noise_0, delta_pos_noise_1` — noise field changes

**Sliding window features** — statistics over the last 10 messages per receiver:

- `pos_std` — how much position varies (high for random position attacks)
- `spd_std` — speed variance
- `hed_std` — heading variance
- `msg_rate` — messages per second (very high for DoS flood attacks)

After computing deltas, any row that had no previous message (first message per receiver) is dropped since the diff is NaN.

---

## Step 3 — Group the 20 attack types into 6

20 classes is too many — many types are nearly identical from a single-receiver view. They get merged into 6 groups:

| Group | Attack types included |
|---|---|
| DoSFamily | DoS, DoSRandom, DoSDisruptive, Disruptive, DoSRandomSybil, DoSDisruptiveSybil, DataReplaySybil, GridSybil |
| PositionAttack | ConstPos, ConstPosOffset, RandomPos, RandomPosOffset |
| SpeedManip | ConstSpeed, ConstSpeedOffset, RandomSpeed, RandomSpeedOffset |
| ReplayAttack | DataReplay |
| DelayedMessages | DelayedMessages |
| EventualStop | EventualStop |

DoSFamily is large because 8 types all share the same core behaviour (flooding). Same for Position and Speed — the model can't reliably tell the subtypes apart.

---

## Step 4 — Balance the datasets

Two separate datasets are built for the two models:

**Binary dataset** (for attack vs benign detection):
- Take all 113,477 Benign rows
- Sample 113,477 rows from all attack rows
- Shuffle everything
- Total: 226,954 rows — perfectly balanced 50/50

**Multiclass dataset** (for attack type classification):
- Take 113,477 rows from each of the 6 groups
- Shuffle everything
- Total: 680,862 rows, perfectly balanced across all 6 groups

---

## Step 5 — Train/test split

Both datasets are split 80% training, 20% testing using stratified split.

- Binary: 181,563 train / 45,391 test
- Multiclass: 544,689 train / 136,173 test

---

## Step 6 — Scale the features

StandardScaler is applied to both datasets. It centers each feature to mean=0 and std=1. The scaler is fit only on the training set and then applied to the test set.

- `scaler_binary.pkl` — used by the binary model (17 raw features)
- `scaler_multi.pkl` — used by the multiclass model (31 features including deltas and window)

At inference time, every incoming BSM gets scaled with these same saved scalers before going into the model.

---

## Step 7 — Train the models

**Binary model — XGBoost:**
- 200 trees, max depth 6, learning rate 0.1
- Result: 100% accuracy, zero false positives and false negatives on test set

**Multiclass model — LightGBM (winner) and XGBoost (compared):**
- Both trained with 5000 trees, early stopping after 100 rounds without improvement
- LightGBM: 68.85% accuracy, saved as `model_multiclass.pkl`
- XGBoost: 66.79% accuracy, not saved
- LightGBM won so it gets saved

The 68.85% accuracy on multiclass is expected. Some groups genuinely overlap in feature space, for example, DoSFamily and some position attacks share similar window statistics in certain scenarios.
