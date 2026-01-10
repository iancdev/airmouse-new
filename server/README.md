# AirMouse Server

Python server that receives sensor/camera data from the phone and controls the OS mouse.

Run from `server/`:

- `python -m airmouse_server --static-dir ../client/out --host 0.0.0.0 --port 8000`

HTTPS (dev, self-signed CA + cert):

- `python -m airmouse_server --static-dir ../client/out --dev-ssl`
