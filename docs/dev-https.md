# Local HTTPS for camera testing

`getUserMedia` needs a secure context. `http://localhost:3000` already is one, so the
laptop webcam works with the local Docker stack. A phone hitting `http://<lan-ip>:3000`
is not, so the Aadhaar scanner cannot open the camera there.

This overlay serves the whole app from one HTTPS origin over Tailscale, which iOS and
Android both trust with no certificate install.

## One-time setup

1. Install Tailscale on this machine and on both phones, signed into the same account
   (free personal plan).
2. In the Tailscale admin console, enable **MagicDNS** and **HTTPS Certificates**.
3. Note the machine's name: `tailscale status --json | jq -r .Self.DNSName`.

## Each session

```
tailscale serve --bg --https=443 http://localhost:8080
DEV_HTTPS_ORIGIN=https://<machine>.<tailnet>.ts.net \
  docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.https.yml up -d --build --wait
```

Open `$DEV_HTTPS_ORIGIN` on either phone. Stop sharing with `tailscale serve --https=443 off`.

## How it works

Caddy listens on localhost port 8080 and forwards to the static nginx frontend, which
proxies `/api/*` to FastAPI. This matches the production [Caddyfile](../Caddyfile).
The browser uses the page origin for API calls, so phone requests use the same HTTPS
address without mixed content or cross-origin requests.

`COOKIE_SECURE=true` in this overlay, so log in through the HTTPS origin — the auth
cookie will not be set over plain `http://localhost:3000` while it is active.
