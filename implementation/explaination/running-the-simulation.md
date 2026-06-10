# Running the Simulation

The simulation has two parts — a Python backend and a React frontend. Both need to be running at the same time.

---

## Backend

The backend runs the ML models and handles the WebSocket connection to the browser.

first thing is to install the dependencies

```bash
cd simulation/backend
pip install -r requirements.txt
```

Then start it:

```bash
uvicorn main:app --reload --port 8000
```

You should see something like:
```
✓ ML models loaded
✓ Benign pool loaded (600 rows)
Uvicorn running on http://0.0.0.0:8000
```

If the models fail to load it means the .pkl files are not in the project root. Make sure model_binary.pkl, model_multiclass.pkl, and the scaler files are one level above the simulation folder.

---

## Frontend

You need Node.js (v18 or later) and npm installed. If you don't have them:

**macOS (via Homebrew):**
```bash
brew install node
```

**Or download directly from** [nodejs.org](https://nodejs.org) — the LTS version includes npm.

Verify the install:
```bash
node --version
npm --version
```

Open a second terminal and run:

```bash
cd simulation/frontend
npm install
npm run dev
```

Then open your browser and go to:

```
http://localhost:5173
```

---

## Notes

- Start the backend before the frontend
- Both terminals need to stay open while using the simulation
- If you get a "disconnected" status in the browser, the backend is not running
- The backend needs to be on port 8000, the frontend is hardcoded to connect there
