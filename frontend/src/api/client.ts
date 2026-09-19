import type {
  AreaConfig,
  AreaState,
  AuthStatus,
  ConsumptionNode,
  EnergyStatus,
  GatewayConfig,
  GatewayConfigOut,
  LevelPoint,
  PhasePoint,
  PowerPoint,
  PricesResponse,
  TemperaturePoint,
  TestResult,
  UpdateStatus,
} from "./types";

const BASE = "/api";

/** Thrown when the API rejects a request for want of a valid session. */
export class UnauthorizedError extends Error {
  constructor() {
    super("Not signed in");
    this.name = "UnauthorizedError";
  }
}

/** Notified whenever a request comes back 401, so the app can show the login. */
type AuthListener = () => void;
const authListeners = new Set<AuthListener>();

export function onUnauthorized(listener: AuthListener): () => void {
  authListeners.add(listener);
  return () => authListeners.delete(listener);
}

/** Pull a human-readable message out of FastAPI's {"detail": …} envelope. */
function describe(status: number, text: string): string {
  try {
    const detail = JSON.parse(text)?.detail;
    if (typeof detail === "string") return detail;
    if (detail) return JSON.stringify(detail);
  } catch {
    // not JSON — fall through to the raw body
  }
  return text || String(status);
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
    // Send the session cookie, and let the browser store a new one.
    credentials: "same-origin",
  });

  if (res.status === 401) {
    authListeners.forEach((fn) => fn());
    throw new UnauthorizedError();
  }

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(describe(res.status, text));
  }

  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

export async function getAuthStatus(): Promise<AuthStatus> {
  // Deliberately not via request(): a 401 here is an answer, not a failure.
  const res = await fetch(`${BASE}/auth/status`, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`Could not reach the backend (${res.status})`);
  return res.json() as Promise<AuthStatus>;
}

export async function setupPassword(password: string): Promise<void> {
  await request<{ ok: boolean }>("POST", "/auth/setup", { password });
}

export async function login(password: string): Promise<void> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
    credentials: "same-origin",
  });
  // A wrong password is a 401 that must surface as a message, not as a
  // "you have been signed out" event.
  if (!res.ok) {
    throw new Error(describe(res.status, await res.text().catch(() => "")));
  }
}

export async function logout(): Promise<void> {
  await request<{ ok: boolean }>("POST", "/auth/logout");
}

export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<void> {
  const res = await fetch(`${BASE}/auth/password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw new Error(describe(res.status, await res.text().catch(() => "")));
  }
}

// ---------------------------------------------------------------------------
// Gateway
// ---------------------------------------------------------------------------

export async function getGateway(): Promise<GatewayConfigOut | null> {
  return request<GatewayConfigOut | null>("GET", "/gateway");
}

export async function saveGateway(cfg: GatewayConfig): Promise<GatewayConfigOut> {
  return request<GatewayConfigOut>("POST", "/gateway", cfg);
}

export async function testGateway(cfg: GatewayConfig): Promise<TestResult> {
  return request<TestResult>("POST", "/gateway/test", cfg);
}

export async function deleteGateway(): Promise<void> {
  return request<void>("DELETE", "/gateway");
}

// ---------------------------------------------------------------------------
// Live area state
// ---------------------------------------------------------------------------

export async function getAreas(): Promise<AreaState[]> {
  return request<AreaState[]>("GET", "/areas");
}

export async function setPreset(
  areaId: number,
  preset: number,
  fadeMs = 1000
): Promise<void> {
  return request<void>("POST", `/areas/${areaId}/preset`, {
    preset,
    fade_ms: fadeMs,
  });
}

export async function setLevel(
  areaId: number,
  channel: number,
  level: number,
  fadeMs = 500
): Promise<void> {
  return request<void>("POST", `/areas/${areaId}/level`, {
    channel,
    level,
    fade_ms: fadeMs,
  });
}

export async function setSetpoint(
  areaId: number,
  setpoint: number
): Promise<void> {
  return request<void>("POST", `/areas/${areaId}/setpoint`, { setpoint });
}

// ---------------------------------------------------------------------------
// Area configuration CRUD
// ---------------------------------------------------------------------------

export async function getConfigAreas(): Promise<AreaConfig[]> {
  return request<AreaConfig[]>("GET", "/config/areas");
}

export async function createArea(area: Omit<AreaConfig, "order"> & { order?: number }): Promise<AreaConfig> {
  return request<AreaConfig>("POST", "/config/areas", area);
}

export async function updateArea(areaId: number, area: AreaConfig): Promise<AreaConfig> {
  return request<AreaConfig>("PUT", `/config/areas/${areaId}`, area);
}

export async function deleteArea(areaId: number): Promise<void> {
  return request<void>("DELETE", `/config/areas/${areaId}`);
}

// ---------------------------------------------------------------------------
// App settings
// ---------------------------------------------------------------------------

export async function getAppSettings(): Promise<{ polling_interval_seconds: number }> {
  return request<{ polling_interval_seconds: number }>("GET", "/settings");
}

export async function saveAppSettings(s: { polling_interval_seconds: number }): Promise<{ polling_interval_seconds: number }> {
  return request<{ polling_interval_seconds: number }>("POST", "/settings", s);
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

export async function getTemperatureHistory(
  areaId: number,
  range: string
): Promise<TemperaturePoint[]> {
  return request<TemperaturePoint[]>(
    "GET",
    `/history/temperature?area_id=${areaId}&range=${range}`
  );
}

export async function getLevelHistory(
  areaId: number,
  channel: number,
  range: string
): Promise<LevelPoint[]> {
  return request<LevelPoint[]>(
    "GET",
    `/history/level?area_id=${areaId}&channel=${channel}&range=${range}`
  );
}

// ---------------------------------------------------------------------------
// Energy (Tibber)
// ---------------------------------------------------------------------------

export async function getEnergyStatus(): Promise<EnergyStatus> {
  return request<EnergyStatus>("GET", "/energy/status");
}

export async function getEnergyPrices(): Promise<PricesResponse> {
  return request<PricesResponse>("GET", "/energy/prices");
}

export async function getEnergyConsumption(
  resolution = "HOURLY",
  last = 24
): Promise<ConsumptionNode[]> {
  return request<ConsumptionNode[]>(
    "GET",
    `/energy/consumption?resolution=${resolution}&last=${last}`
  );
}

export async function getEnergyHistoryPower(range: string): Promise<PowerPoint[]> {
  return request<PowerPoint[]>("GET", `/energy/history/power?range=${range}`);
}

export async function getEnergyHistoryPhases(range: string): Promise<PhasePoint[]> {
  return request<PhasePoint[]>("GET", `/energy/history/phases?range=${range}`);
}

export async function getEnergyHomes(
  token?: string
): Promise<{ id: string; address: { address1: string; city: string } }[]> {
  const url = token
    ? `/energy/homes?token=${encodeURIComponent(token)}`
    : "/energy/homes";
  return request<{ id: string; address: { address1: string; city: string } }[]>(
    "GET",
    url
  );
}

export async function saveEnergySettings(
  token: string,
  homeId: string
): Promise<void> {
  return request<void>("POST", "/energy/settings", { token, home_id: homeId });
}

// ---------------------------------------------------------------------------
// Software update
// ---------------------------------------------------------------------------

export async function checkUpdate(): Promise<UpdateStatus> {
  return request<UpdateStatus>("GET", "/update");
}

export async function applyUpdate(): Promise<{ status: string }> {
  return request<{ status: string }>("POST", "/update/apply");
}

// ---------------------------------------------------------------------------
// Backup
// ---------------------------------------------------------------------------

export async function importBackup(data: unknown): Promise<{
  areas_imported: number;
  temperature_points: number;
  level_points: number;
}> {
  return request<{ areas_imported: number; temperature_points: number; level_points: number }>(
    "POST",
    "/backup/import",
    data
  );
}
