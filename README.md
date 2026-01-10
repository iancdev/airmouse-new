# AirMouse

Use a phone (iOS/Android) as a desk-surface mouse by streaming sensor + camera data to a computer server that drives the OS cursor.

## Project layout

- `server/`: Python server (WebSocket + mouse control + optional vision)
- `client/`: Next.js web client (opens on the phone)
- `docs/`: product notes

## Quick start (local network)

1) Build the web client:

- `cd client`
- `npm install`
- `npm run build`

2) Install server deps:

- `cd ../server`
- `python3 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`

3) Run the server (serves the client at `/`):

- `python -m airmouse_server --static-dir ../client/out --host 0.0.0.0 --port 8000`

4) On your phone (same Wi‑Fi), open:

- `http://<computer-ip>:8000/`

Then tap “Connect”.

## HTTPS (recommended for camera + iOS sensors)

Most browsers require a secure context for `getUserMedia()` (camera). iOS also requires explicit motion/orientation permission prompts.

Easiest dev option (auto-generates a local CA + server cert):

- `python -m airmouse_server --static-dir ../client/out --dev-ssl`

This writes certs to `server/.certs/` and prints the CA cert path. Install/trust that CA cert on your phone, then open `https://<computer-ip>:8000/`.

## Notes

- Sensor selection: enable/disable camera + IMU sources on the connect screen; when multiple are enabled, movement is validated via a majority direction agreement vote.
- macOS: grant Accessibility permissions to Terminal/Python for `pyautogui` to control the cursor.

## Status

Work in progress.
