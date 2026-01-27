IEC61850 Client GUI
-------------------

A lightweight Flask-based web UI to explore and interact with an IEC 61850 server using the repository's client code. It can connect to a WebSocket endpoint, fetch and display model data (LD/LN tree), and monitor protocol messages.

Overview
- Backend: `Flask` app (`iec61850-gui/app.py`) serving HTML/JS from `templates/` and `static/`.
- Client: uses `Endpoint.WebSocketEndpoint` + `IEC61850.client.IEC61850Client`.
- Default port: `5000` (configurable via `PORT` env var).

Requirements
- Python 3.10+
- Project dependencies: `requirements.txt` in repo root
- Flask (not in `requirements.txt`): install separately

Setup (recommended virtual environment)
```bash
# From repo root
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install Flask

# Ensure imports work (adds repo paths to PYTHONPATH)
./setup.sh
```

Run
```bash
# From repo root
export PORT=5000   # optional; defaults to 5000
python iec61850-gui/app.py
# App listens on 0.0.0.0:$PORT
```
Open `http://localhost:5000` in your browser.

Connect from UI
---------------
Use the connection form:
- Host: IEC 61850 WebSocket server host
- Port: IEC 61850 WebSocket server port
- CP: CP path (e.g., `cp`)

Click "Connect" to start a client connection. The backend manages the endpoint/client lifecycle and logs recent actions and messages.

Features
- Build and browse the IED model tree (LD/LN).
- Monitor sent/received TPAA protocol messages.
- Optional TLS and OAuth support when configured on the server side.

Troubleshooting
- Import errors: run `./setup.sh` to set `PYTHONPATH` or export paths manually.
- Connection issues: verify server host/port and reachability; check TLS/OAuth settings if enabled.
- Port conflicts: set `PORT` to a free port before starting the app.
