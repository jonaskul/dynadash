import type {
  AreaConfig,
  AreaState,
  GatewayConfig,
  GatewayConfigOut,
  LevelPoint,
  TemperaturePoint,
  TestResult,
} from "./types";

const BASE = "/api";

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${method} ${path} → ${res.status}: ${text}`);
  }

  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return res.json() as Promise<T>;
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
