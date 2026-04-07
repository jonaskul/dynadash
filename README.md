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

- Proxmox VE host with internet access
- A Dynalite Ethernet Gateway reachable on the local network

---

## Installation

Run this **on the Proxmox VE host** (not inside a container):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jonaskul/dynadash/main/run.sh)"
```

The script will:
1. Ask whether you want default settings or advanced (CT ID, RAM, disk, CPU, network)
2. Download the latest Debian 13 LXC template (falls back to Debian 12 if 13 is unavailable)
3. Create and start an unprivileged LXC container
4. Configure **root auto-login** on the PVE console
5. Wait for DHCP and DNS before proceeding
6. Clone DynaDash and run the full installer inside the container
7. Print the dashboard URL and update command when done

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

`install.sh` (which runs inside the container) will:

1. Install system packages (`python3`, `nginx`, `curl`, `jq`)
2. Install **Node.js 20 LTS** via NodeSource
3. Add the InfluxData apt repo and install `influxdb2` + `influxdb2-cli`
4. Initialise InfluxDB and write `backend/config.yaml` with the generated token
5. Create a Python virtual environment and install backend dependencies
6. Build the React frontend (`npm install && npm run build`) and deploy to `/var/www/dynadash`
7. Configure nginx (port 80, proxy `/api/` to FastAPI, SPA fallback)
8. Install and start the `dynadash-backend` systemd service

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

This pulls the latest code, reinstalls Python deps, rebuilds the frontend, and restarts all services.

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
systemctl restart dynadash-backend
```

A commented example is provided at `config.yaml.example`.

---

## Service management (inside the container)

```bash
# Backend logs
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
               │              ├── Dynalite CGI gateway (HTTP/Basic Auth)
               │              └── InfluxDB v2 (localhost:8086)
               └── /*     → /var/www/dynadash (React SPA)
```

- Installed to `/opt/dynadash` inside the LXC container
- Gateway credentials stored in `backend/data/gateway.json` (not in source control)
- Area definitions stored in `backend/data/areas.json` (not in source control)
- All time-series data lives in InfluxDB under the `dynadash` bucket

---

## Security note

DynaDash is designed for use on a private LAN. CORS is open (`*`) and there is no authentication on the dashboard itself. Do not expose port 80 directly to the internet.
