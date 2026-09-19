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

1. Open the dashboard URL. The first screen asks you to **choose a dashboard
   password** (at least 10 characters), shared by everyone in the household.

   Do this straight after installing: until a password exists the API refuses
   every request, and whoever reaches the dashboard first is the one who gets to
   set it. You can change it later under **Settings → Security**, which also
   signs out every other device.
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

## Security

DynaDash is designed for private LAN use. It is **not** hardened for exposure to
the internet — traffic is plain HTTP, so the password and session cookie travel
unencrypted. Do not forward port 80.

What is in place:

- **Dashboard password.** Every `/api/` route except `/api/health` and the login
  endpoints requires a session. The password is stored as an scrypt hash;
  sessions are held as hashes too, expire after 30 days, and survive a restart so
  an update does not sign everyone out. Repeated failed logins lock that address
  out for five minutes.
- **The backend does not run as root.** It runs as the system user `dynadash`,
  under a systemd sandbox where the whole filesystem is read-only apart from
  `backend/data`, and with no capabilities.
- **Narrow privilege for the updater.** The GUI updater needs git and systemd, so
  the backend may run `scripts/dynadash-admin` — root-owned, not writable by the
  service user — through sudo, with its three actions (`fetch`, `revs`, `apply`)
  listed verbatim in `/etc/sudoers.d/dynadash`. Nothing else is permitted.
- **CORS** is restricted to localhost and private address ranges.

Worth knowing: the update flow deploys whatever `main` currently holds, so
control of the GitHub repository means control of this machine. That is inherent
to a self-updating deployment, not something the sandbox can contain.
