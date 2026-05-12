// ---------------------------------------------------------------------------
// Gateway
// ---------------------------------------------------------------------------

export interface GatewayConfig {
  ip: string;
  scheme: "http" | "https";
  verify_ssl: boolean;
  username?: string;
  password?: string;
}

export interface GatewayConfigOut {
  ip: string;
  scheme: "http" | "https";
  verify_ssl: boolean;
  username?: string;
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
  watts: number;
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
  watts: number;
  gateway_reachable: boolean;
}

export interface ThermostatAreaState {
  id: number;
  name: string;
  type: "thermostat";
  current_preset: number | null;
  current_temp: number | null;
  setpoint: number | null;
  temp_min: number;
  temp_max: number;
  presets: Record<string, string>;
  watts: number;
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

// ---------------------------------------------------------------------------
// Energy (Tibber)
// ---------------------------------------------------------------------------

export interface EnergyStatus {
  configured: boolean;
  home_id: string | null;
  pulse_connected: boolean;
  last_pulse_ts: string | null;
  current_price: { total: number; level: string; currency: string } | null;
  current_power: number | null;
}

export interface PriceEntry {
  total: number;
  energy: number;
  tax: number;
  startsAt: string;
  level: string;
  currency: string;
}

export interface PricesResponse {
  current: PriceEntry | null;
  today: PriceEntry[];
  tomorrow: PriceEntry[];
}

export interface ConsumptionNode {
  from: string;
  to: string;
  cost: number | null;
  unitPrice: number | null;
  consumption: number | null;
  currency: string;
}

export interface PowerPoint {
  time: string;
  power: number | null;
}

export interface PhasePoint {
  time: string;
  voltagePhase1?: number | null;
  voltagePhase2?: number | null;
  voltagePhase3?: number | null;
  currentL1?: number | null;
  currentL2?: number | null;
  currentL3?: number | null;
}
