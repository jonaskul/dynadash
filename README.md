# DynaDash

A home automation dashboard for Dynalite lighting, HVAC control, and electricity monitoring. React + Vite + Tailwind frontend, Python FastAPI backend, InfluxDB v2 for time-series history.

## Features

- **Control** — lighting preset and channel-level control; thermostat setpoint adjustment with 24h min/max and trend indicator
- **History** — all areas as stacked charts sorted by Display Order; 1h / 6h / 24h / 7d ranges
- **Energy** — Tibber electricity prices (hourly bar chart with price-level colours), live Pulse power (2 s polling), today's cost and usage, power history (1h / 6h / 24h / 7d), and per-phase current and voltage history
- **Area Manager** — add, edit, and delete areas from the UI; supports rated wattage for consumption display
- **Settings** — gateway config, polling interval (1–60 min), light/dark mode, 24h/12h clock
- **Import / Export** — back up all areas and history to a single JSON file; restore on any instance
- **No mandatory setup** — configure the gateway from Settings at any time; no config files required

---

## Prerequisites

- Proxmox VE host with internet access
- A Dynalite Ethernet Gateway (PDEG or compatible) reachable on the local network
- *(Optional)* A Tibber account with API access for the Energy tab

---

## Installation

Run on the **Proxmox VE host**:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jonaskul/dynadash/main/run.sh)"
```

The script creates an unprivileged Debian LXC container, installs DynaDash, configures root auto-login on the PVE console, enables SSH, and prints the dashboard URL and SSH credentials when done.

> **Save the SSH password** shown at the end — it will not be displayed again.

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

Advanced settings (CT ID, RAM, disk, CPU, static IP) can be configured when prompted.

---

## First-launch setup

1. Open the dashboard URL — you land directly on the **Control** view.
2. Go to **Settings → Gateway Configuration** and enter your gateway IP address.
   - Enable **Use HTTPS** if your gateway requires it.
   - Enable **Ignore certificate errors** for self-signed certificates.
   - Enable **Require authentication** only if your gateway uses Basic Auth (most don't).
3. Click **Test** to verify connectivity, then **Save**.
4. Go to **Areas → Add Area** to define your first room:
   - **Area ID** — the DyNet area number (1–65535)
   - **Name** — display name (e.g. "Living Room")
   - **Type** — Lighting or Thermostat
   - **Channels** — number of channels (lighting only)
   - **Rated wattage** — optional; enables live watt consumption display
   - **Presets** — map preset numbers to labels (e.g. `1 → Full`, `2 → Evening`)
   - **Temp min/max** — setpoint limits (thermostat only)
5. Go to **Control** to see your area cards and start controlling.

### Energy tab (optional)

1. Go to **Energy** and click **Connect Tibber**.
2. Paste your Tibber API token (find it at [developer.tibber.com](https://developer.tibber.com/settings/access-token)).
3. Click **Load homes**, select your home, and click **Save**.

Electricity prices and consumption history appear immediately. If you have a Tibber Pulse, live power data starts streaming within a few seconds.

---

## Updating

Run on the **Proxmox VE host**, replacing `<CTID>` with your container ID:

```bash
pct exec <CTID> -- /opt/dynadash/update.sh
```

Or from inside the container:

```bash
/opt/dynadash/update.sh
```

The script checks if the code has changed and exits immediately if already up to date. Pass `--force` to rebuild and restart regardless:

```bash
/opt/dynadash/update.sh --force
```

All output is appended to `/var/log/dynadash-update.log`.

---

## Polling

Areas are polled in sequence with a 2-second gap between each to avoid overloading the gateway. The interval is adjustable in **Settings → Polling Interval** (1–60 minutes, default 1 minute) and takes effect immediately without a restart. The backend also polls once on startup so the dashboard shows live state right away.

---

## Service management

Run these inside the container:

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
               ├── /api/  → FastAPI (uvicorn :8000)
               │              ├── Dynalite CGI gateway (HTTP or HTTPS)
               │              ├── Tibber API / WebSocket (optional)
               │              └── InfluxDB v2 (localhost:8086)
               └── /*     → /var/www/dynadash (React SPA)
```

Data files in `backend/data/` (not in source control):

| File | Contents |
|---|---|
| `gateway.json` | Gateway IP, scheme, auth |
| `areas.json` | Area definitions |
| `settings.json` | Polling interval |
| `tibber.db` | Tibber token and home ID (SQLite) |

---

## Security note

DynaDash is designed for private LAN use. CORS is open (`*`) and there is no dashboard authentication. Do not expose port 80 to the internet.
