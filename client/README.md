# AirMouse Client

Next.js web client intended to run in a mobile browser.

Run locally (dev):

- `npm install`
- `npm run dev`

Dev over HTTPS (required for camera + iOS motion/orientation):

- `npm run dev -- --experimental-https --hostname 0.0.0.0`

To reuse the server dev cert (so your phone only trusts one CA):

- `npm run dev -- --experimental-https --experimental-https-key ../server/.certs/airmouse-server-key.pem --experimental-https-cert ../server/.certs/airmouse-server-cert.pem --experimental-https-ca ../server/.certs/airmouse-ca-cert.pem --hostname 0.0.0.0`
