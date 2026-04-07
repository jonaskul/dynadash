// ---------------------------------------------------------------------------
// Gateway
// ---------------------------------------------------------------------------

export interface GatewayConfig {
  ip: string;
  scheme: "http" | "https";
  verify_ssl: boolean;
}

export interface GatewayConfigOut {
  ip: string;
  scheme: "http" | "https";
  verify_ssl: boolean;
}

export interface TestResult {
  success: boolean;
  message: string;
}

// ---------------------------------------------------------------------------
// Area configuration (persisted shape from /api/config/areas)
// ---------------------------------------------------------------------------

export type AreaType = "lighting" | "thermostat";

export interface AreaConfig {
  id: number;
  name: string;
  type: AreaType;
  channels: number;
  presets: Record<string, string>; // preset number (string key) → label
  temp_min: number;
  temp_max: number;
  order: number;
}

// ---------------------------------------------------------------------------
// Live area state (from /api/areas — merged with poller state)
// ---------------------------------------------------------------------------

export interface ChannelState {
  channel: number;
  level: number;
}

export interface LightingAreaState {
  id: number;
  name: string;
  type: "lighting";
  current_preset: number | null;
  channels: ChannelState[];
  num_channels: number;
  presets: Record<string, string>;
  gateway_reachable: boolean;
}

export interface ThermostatAreaState {
  id: number;
  name: string;
  type: "thermostat";
  current_temp: number | null;
  setpoint: number | null;
  temp_min: number;
  temp_max: number;
  presets: Record<string, string>;
  gateway_reachable: boolean;
}

export type AreaState = LightingAreaState | ThermostatAreaState;

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

export interface TemperaturePoint {
  time: string;
  temperature: number | null;
  setpoint: number | null;
}

export interface LevelPoint {
  time: string;
  level: number | null;
}
