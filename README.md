# DynaDash

A professional home automation dashboard for Dynalite lighting and HVAC (thermostat) control systems. Built with React + Vite + Tailwind on the frontend and Python FastAPI on the backend, with InfluxDB v2 for time-series history.

## Features

- **Control view** — live lighting preset and channel-level control; thermostat setpoint adjustment
- **History view** — temperature/setpoint line charts and lighting level area charts (1h / 6h / 24h / 7d)
- **Area Manager** — add, edit, and delete Dynalite areas from the UI (no config files)
- **Settings** — gateway connection management with in-app test
- **Onboarding** — first-launch setup screen; no manual config editing required
- **Dark glass-morphism UI** — electric blue accents, smooth transitions, fully responsive

---

## Prerequisites

- Debian 11 / 12 or Ubuntu 22.04+ LXC container (or VM)
- Root access
- Internet connection (for apt packages and npm)
- A Dynalite Ethernet Gateway reachable on the local network

---

## Installation

Paste this one-liner into your PVE LXC console (as root):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jonaskul/dynadash/main/run.sh)"
```

DynaDash installs to `/opt/dynadash`. The same command also updates an existing installation.

`install.sh` will:

1. Install system packages (`python3`, `nodejs`, `npm`, `nginx`, `influxdb2`)
2. Initialise InfluxDB and write a `config.yaml` with the generated token
3. Create a Python virtual environment and install backend dependencies
4. Build the React frontend and deploy it to `/var/www/dynadash`
5. Configure nginx (port 80, proxy `/api/` to FastAPI)
6. Install and start the `dynadash-backend` systemd service

At the end it prints the dashboard URL, e.g. `http://192.168.1.10/`.

---

## First-launch setup (in the UI)

1. Open the dashboard URL in your browser.
2. The **setup screen** appears — enter your gateway IP, username, and password.
3. Click **Test Connection** to verify, then **Save & Continue**.
4. You land on the **Area Manager**. Click **Add Area** to define your first room:
   - **Area ID** — the DyNet area number (1–65535)
   - **Name** — display name (e.g. "Living Room")
   - **Type** — Lighting or Thermostat
   - **Channels** — number of DALI/DyNet channels (lighting only)
   - **Presets** — map preset numbers to labels (e.g. `1 → Full`, `2 → Evening`)
   - **Temp min/max** — setpoint limits (thermostat only)
5. Go to **Control** to see your area cards and start controlling.

---

## Editing `config.yaml`

`backend/config.yaml` is written automatically by `install.sh`. You normally don't need to edit it. If you do:

```yaml
influxdb:
  url: "http://localhost:8086"   # InfluxDB v2 URL
  token: "your-token-here"       # Admin token (written by install.sh)
  org: "home"                    # InfluxDB organisation
  bucket: "dynadash"             # InfluxDB bucket

polling_interval_seconds: 10     # How often to poll the gateway
```

Restart the backend after editing:

```bash
sudo systemctl restart dynadash-backend
```

A commented example is provided at `config.yaml.example`.

---

## Updating

Run the same one-liner again — it detects the existing install and updates instead:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jonaskul/dynadash/main/run.sh)"
```

Or from the install directory directly:

```bash
sudo /opt/dynadash/update.sh
```

Both pull the latest code, reinstall Python deps, rebuild the frontend, and restart all services.

---

## Service management

```bash
# Backend logs
sudo journalctl -u dynadash-backend -f

# Restart backend
sudo systemctl restart dynadash-backend

# Reload nginx
sudo nginx -t && sudo systemctl reload nginx
```

---

## Architecture

```
Browser → nginx (port 80)
               │
               ├── /api/  → FastAPI (uvicorn, port 8000)
               │              ├── Dynalite CGI gateway (HTTP/Basic Auth)
               │              └── InfluxDB v2 (localhost:8086)
               └── /*     → /var/www/dynadash (React SPA)
```

- Gateway credentials are stored in `backend/data/gateway.json` (not in source control)
- Area definitions are stored in `backend/data/areas.json` (not in source control)
- All time-series data lives in InfluxDB under the `dynadash` bucket

---

## Security note

DynaDash is designed for use on a private LAN. CORS is open (`*`) and there is no authentication on the dashboard itself. Do not expose port 80 directly to the internet.
