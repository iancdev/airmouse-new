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

3) Run the server (serves the client at `/app/`):

- `python -m airmouse_server --static-dir ../client/out --host 0.0.0.0 --port 8000`

4) On your phone (same Wi‑Fi), open:

- `http://<computer-ip>:8000/`

Then tap “Open AirMouse” → “Connect”.

## HTTPS (recommended for camera + iOS sensors)

Most browsers require a secure context for `getUserMedia()` (camera). iOS also requires explicit motion/orientation permission prompts.

Run the server with HTTPS/WSS:

- Generate a cert (recommended: `mkcert`), or quick self-signed:
  - `openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=<computer-ip>"`
- Start:
  - `python -m airmouse_server --static-dir ../client/out --ssl-keyfile key.pem --ssl-certfile cert.pem`

Then open `https://<computer-ip>:8000/` on your phone.

## Notes

- Sensor selection: enable/disable camera + IMU sources on the connect screen; when multiple are enabled, movement is validated via a majority direction agreement vote.
- macOS: grant Accessibility permissions to Terminal/Python for `pyautogui` to control the cursor.

## Status

Work in progress.
