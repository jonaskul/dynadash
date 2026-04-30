# DynaDash

A professional home automation dashboard for Dynalite lighting and HVAC (thermostat) control. Built with React + Vite + Tailwind on the frontend and Python FastAPI on the backend, with InfluxDB v2 for time-series history.

## Features

- **Control view** — live lighting preset and channel-level control; thermostat setpoint adjustment with active preset badge and watt consumption display
- **History view** — temperature/setpoint line charts and lighting level area charts (1h / 6h / 24h / 7d)
- **Area Manager** — add, edit, and delete Dynalite areas from the UI (no config files required); supports rated wattage per area for consumption calculation
- **Settings** — gateway configuration (IP, HTTP/HTTPS, optional Basic Auth, SSL cert verification), polling interval slider (1–60 min), build version
- **No mandatory setup** — opens directly to the dashboard; configure the gateway from Settings at any time
- **Dark glass-morphism UI** — electric blue accents, 24h clock, smooth transitions, fully responsive

---

## Prerequisites

- Proxmox VE host with internet access
- A Dynalite Ethernet Gateway (PDEG or compatible) reachable on the local network

---

## Installation

Run this **on the Proxmox VE host** (not inside a container):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jonaskul/dynadash/main/run.sh)"
```

The script will:
1. Ask whether you want default settings or advanced (CT ID, RAM, disk, CPU, network)
2. Download the latest Debian 13 LXC template (falls back to Debian 12 if unavailable)
3. Create and start an unprivileged LXC container
4. Configure **root auto-login** on the PVE console
5. Wait for DHCP and DNS before proceeding
6. Clone DynaDash and run the full installer inside the container
7. Generate a random root password, install SSH, and print the dashboard URL + SSH credentials when done

**Default container settings:**

| Setting | Value |
|---|---|
| Hostname | `dynadash` |
| RAM | 1024 MB |
| Swap | 512 MB |
| Disk | 8 GB |
| CPU | 2 cores |
| Network | vmbr0, DHCP |
| Install path | `/opt/dynadash` |

`install.sh` (runs inside the container) will:

1. Install system packages (`python3`, `nginx`, `curl`, `jq`)
2. Install **Node.js 20 LTS** via NodeSource
3. Add the InfluxData apt repo and install `influxdb2` + `influxdb2-cli`
4. Initialise InfluxDB and write `backend/config.yaml` with the generated token
5. Create a Python virtual environment and install backend dependencies
6. Build the React frontend (`npm install && npm run build`) and deploy to `/var/www/dynadash`
7. Configure nginx (port 80, proxy `/api/` to FastAPI, SPA fallback)
8. Install and start the `dynadash-backend` systemd service

---

## First-launch setup (in the UI)

1. Open the dashboard URL in your browser — you land directly on the **Control** view.
2. Go to **Settings** and enter your gateway IP address.
   - Enable **Use HTTPS** if your gateway requires it.
   - Enable **Ignore certificate errors** if using a self-signed certificate.
   - Enable **Require authentication** only if your gateway demands Basic Auth (most don't).
3. Click **Test** to verify, then **Save**.
4. Go to **Areas** and click **Add Area** to define your first room:
   - **Area ID** — the DyNet area number (1–65535)
   - **Name** — display name (e.g. "Living Room")
   - **Type** — Lighting or Thermostat
   - **Channels** — number of channels (lighting only)
   - **Rated wattage** — optional; enables live consumption display on the card
   - **Presets** — map preset numbers to labels (e.g. `1 → Full`, `2 → Evening`)
   - **Temp min/max** — setpoint limits (thermostat only)
5. Go to **Control** to see your area cards and start controlling.

---

## Updating

Run on the **Proxmox VE host**, replacing `<CTID>` with your container ID:

```bash
pct exec <CTID> -- /opt/dynadash/update.sh
```

Or enter the container first:

```bash
pct enter <CTID>
/opt/dynadash/update.sh
```

`update.sh` will:
1. Check if there is anything new to pull — exits immediately with "Already up to date" if not
2. Back up `backend/data/` before pulling, then restore it after
3. Reinstall Python deps, rebuild the frontend, and redeploy
4. Validate `backend/main.py` syntax before restarting the service
5. Wait up to 20 seconds for the backend to come back up

Pass `--force` to rebuild and restart even when the code is already current:

```bash
/opt/dynadash/update.sh --force
```

All output is also appended to `/var/log/dynadash-update.log`.

---

## Polling

The backend polls all configured areas in sequence, with a **2-second pause between each area** to avoid overloading the gateway. The polling interval (how often a full cycle runs) can be adjusted in **Settings → Polling Interval** (1–60 minutes, default 1 minute). The change takes effect immediately without a restart.

The backend also does an **immediate poll on startup** so the dashboard shows real state as soon as it loads.

---

## `config.yaml`

`backend/config.yaml` is written automatically by `install.sh`. You normally don't need to edit it manually:

```yaml
influxdb:
  url: "http://localhost:8086"
  token: "your-token-here"      # written by install.sh
  org: "home"
  bucket: "dynadash"

polling_interval_seconds: 60    # fallback default; overridden by Settings UI
```

Restart the backend after manual edits:

```bash
systemctl restart dynadash-backend
```

---

## Service management (inside the container)

```bash
# Live backend logs
journalctl -u dynadash-backend -f

# Restart backend
systemctl restart dynadash-backend

# Reload nginx
nginx -t && systemctl reload nginx
```

---

## Architecture

```
Browser → nginx (port 80)
               │
               ├── /api/  → FastAPI (uvicorn, port 8000)
               │              ├── Dynalite CGI gateway (HTTP or HTTPS)
               │              └── InfluxDB v2 (localhost:8086)
               └── /*     → /var/www/dynadash (React SPA)
```

- Installed to `/opt/dynadash` inside the LXC container
- Gateway config stored in `backend/data/gateway.json` (not in source control)
- Area definitions stored in `backend/data/areas.json` (not in source control)
- App settings (polling interval) stored in `backend/data/settings.json`
- All time-series data lives in InfluxDB under the `dynadash` bucket

---

## Security note

DynaDash is designed for use on a private LAN. CORS is open (`*`) and there is no authentication on the dashboard itself. Do not expose port 80 directly to the internet.
