import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getEnergyConsumption,
  getEnergyHistoryPhases,
  getEnergyHistoryPower,
  getEnergyHomes,
  getEnergyPrices,
  getEnergyStatus,
  saveEnergySettings,
} from "../api/client";
import type {
  ConsumptionNode,
  EnergyStatus,
  PhasePoint,
  PowerPoint,
  PricesResponse,
} from "../api/types";
import { useUISettings } from "../context/UISettings";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LEVEL_COLORS: Record<string, string> = {
  VERY_CHEAP: "#22c55e",
  CHEAP: "#86efac",
  NORMAL: "#facc15",
  EXPENSIVE: "#f97316",
  VERY_EXPENSIVE: "#ef4444",
};

const LEVEL_LABELS: Record<string, string> = {
  VERY_CHEAP: "Very cheap",
  CHEAP: "Cheap",
  NORMAL: "Normal",
  EXPENSIVE: "Expensive",
  VERY_EXPENSIVE: "Very expensive",
};

const ALL_RANGES = ["1h", "6h", "24h", "7d"] as const;
type HistoryRange = (typeof ALL_RANGES)[number];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function msUntilMidnight(): number {
  const now = new Date();
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  return midnight.getTime() - now.getTime();
}

interface BarEntry {
  hour: number;
  price: number;
  level: string;
  isTomorrow: boolean;
  isCurrent: boolean;
}

function buildChartData(prices: PricesResponse): BarEntry[] {
  const currentHour = new Date().getHours();
  const todayDate = new Date().toDateString();

  const todayBars = prices.today.map((e) => ({
    hour: new Date(e.startsAt).getHours(),
    price: Math.round(e.total * 1000) / 10,
    level: e.level,
    isTomorrow: false,
    isCurrent:
      new Date(e.startsAt).getHours() === currentHour &&
      new Date(e.startsAt).toDateString() === todayDate,
  }));

  const tomorrowBars = prices.tomorrow.map((e) => ({
    hour: new Date(e.startsAt).getHours() + 24,
    price: Math.round(e.total * 1000) / 10,
    level: e.level,
    isTomorrow: true,
    isCurrent: false,
  }));

  return [...todayBars, ...tomorrowBars];
}

function formatTime(iso: string, range: HistoryRange): string {
  const d = new Date(iso);
  if (range === "7d") {
    return d.toLocaleDateString([], { weekday: "short" }) + " " +
      d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

function RangeSelector({
  value,
  onChange,
}: {
  value: HistoryRange;
  onChange: (r: HistoryRange) => void;
}) {
  return (
    <div className="flex rounded-lg border border-slate-200 overflow-hidden dark:border-white/10">
      {ALL_RANGES.map((r) => (
        <button
          key={r}
          onClick={() => onChange(r)}
          className={`px-3 py-1.5 text-sm font-medium transition-colors ${
            r === value
              ? "bg-electric-blue text-navy-900"
              : "bg-white text-slate-500 hover:text-slate-900 hover:bg-slate-50 dark:bg-navy-800 dark:text-slate-400 dark:hover:text-white dark:hover:bg-white/5"
          }`}
        >
          {r}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Spinner
// ---------------------------------------------------------------------------

function Spinner() {
  return (
    <div className="flex h-32 items-center justify-center">
      <div className="h-7 w-7 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// SetupCard
// ---------------------------------------------------------------------------

interface HomeEntry {
  id: string;
  address: { address1: string; city: string };
}

function SetupCard({ onSaved }: { onSaved: () => void }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState("");
  const [homes, setHomes] = useState<HomeEntry[]>([]);
  const [homeId, setHomeId] = useState("");
  const [loadingHomes, setLoadingHomes] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLoadHomes() {
    setError(null);
    setLoadingHomes(true);
    try {
      const result = await getEnergyHomes(token);
      setHomes(result);
      if (result.length > 0) setHomeId(result[0].id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load homes");
    } finally {
      setLoadingHomes(false);
    }
  }

  async function handleSave() {
    setError(null);
    setSaving(true);
    try {
      await saveEnergySettings(token, homeId);
      queryClient.invalidateQueries({ queryKey: ["energy-status"] });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-white/10 dark:bg-navy-800/60 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Connect Tibber</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Enter your Tibber API token to see electricity prices and consumption.
        </p>
        <a
          href="https://developer.tibber.com/settings/access-token"
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1 inline-block text-sm text-electric-blue hover:underline"
        >
          Find your token here ↗
        </a>
      </div>

      <div className="space-y-3">
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="your-tibber-token"
          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-electric-blue focus:outline-none dark:border-white/10 dark:bg-navy-900 dark:text-white dark:placeholder:text-slate-500"
        />

        {homes.length === 0 ? (
          <button
            onClick={handleLoadHomes}
            disabled={!token || loadingHomes}
            className="rounded-lg bg-electric-blue px-4 py-2 text-sm font-medium text-navy-900 transition-opacity disabled:opacity-50"
          >
            {loadingHomes ? "Loading…" : "Load homes"}
          </button>
        ) : (
          <select
            value={homeId}
            onChange={(e) => setHomeId(e.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-electric-blue focus:outline-none dark:border-white/10 dark:bg-navy-900 dark:text-white"
          >
            {homes.map((h) => (
              <option key={h.id} value={h.id}>
                {h.address.address1}, {h.address.city}
              </option>
            ))}
          </select>
        )}

        {homes.length > 0 && (
          <button
            onClick={handleSave}
            disabled={!homeId || saving}
            className="rounded-lg bg-electric-blue px-4 py-2 text-sm font-medium text-navy-900 transition-opacity disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        )}

        {error && <p className="text-sm text-red-500">{error}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatusBar
// ---------------------------------------------------------------------------

function StatusBar({ status }: { status: EnergyStatus }) {
  const level = status.current_price?.level ?? "NORMAL";
  const bgColor = LEVEL_COLORS[level] ?? "#94a3b8";
  const total = status.current_price?.total ?? 0;
  const orePerKwh = (total * 100).toFixed(1);

  return (
    <div
      className="rounded-xl p-5 flex items-center justify-between"
      style={{ backgroundColor: bgColor + "22" }}
    >
      <div>
        <div className="text-3xl font-bold tabular-nums" style={{ color: bgColor }}>
          {orePerKwh} øre/kWh
        </div>
        <div className="text-sm text-slate-500 dark:text-slate-400">
          {LEVEL_LABELS[level] ?? level}
        </div>
      </div>
      <div className="flex items-center gap-4">
        {status.current_power != null && (
          <div className="text-right">
            <div className="text-2xl font-bold tabular-nums text-slate-900 dark:text-white">
              {Math.round(status.current_power)} W
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400">Live power</div>
          </div>
        )}
        <div className="flex items-center gap-1.5">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              status.pulse_connected ? "bg-green-400" : "bg-red-500"
            }`}
          />
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {status.pulse_connected ? "Pulse" : "No Pulse"}
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PriceChart
// ---------------------------------------------------------------------------

function PriceChartSection({ prices }: { prices: PricesResponse }) {
  const { lightMode } = useUISettings();
  const gridColor = lightMode ? "rgba(0,0,0,0.07)" : "rgba(255,255,255,0.06)";
  const axisColor = lightMode ? "rgba(0,0,0,0.45)" : "rgba(255,255,255,0.3)";
  const tooltipStyle = lightMode
    ? { backgroundColor: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, color: "#0f172a", fontSize: 12 }
    : { backgroundColor: "#1e293b", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, color: "#f8fafc", fontSize: 12 };

  const chartData = buildChartData(prices);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm">
      <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">Electricity prices</h2>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={gridColor} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="hour"
            ticks={[0, 6, 12, 18, 24, 30, 36, 42]}
            tickFormatter={(h: number) =>
              `${String(h % 24).padStart(2, "0")}:00`
            }
            tick={{ fill: axisColor, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: gridColor }}
          />
          <YAxis
            tick={{ fill: axisColor, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: gridColor }}
            unit=" øre"
            width={56}
          />
          {prices.tomorrow.length > 0 && (
            <ReferenceLine
              x={24}
              stroke={axisColor}
              strokeDasharray="4 2"
              label={{ value: "Tomorrow", fill: axisColor, fontSize: 10, position: "insideTopRight" }}
            />
          )}
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(h: number) =>
              `${String(h % 24).padStart(2, "0")}:00${h >= 24 ? " (tomorrow)" : ""}`
            }
            formatter={(value: number, _: string, item: { payload?: BarEntry }) => {
              const level = item.payload?.level ?? "";
              return [
                `${(value as number).toFixed(1)} øre/kWh`,
                LEVEL_LABELS[level] ?? level,
              ];
            }}
          />
          <Bar dataKey="price" radius={[3, 3, 0, 0]} maxBarSize={32}>
            {chartData.map((entry, i) => (
              <Cell
                key={i}
                fill={LEVEL_COLORS[entry.level] ?? "#94a3b8"}
                fillOpacity={entry.isTomorrow ? 0.45 : 1}
                stroke={entry.isCurrent ? "#fff" : "none"}
                strokeWidth={entry.isCurrent ? 2 : 0}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatsCards
// ---------------------------------------------------------------------------

function StatsCards({
  status,
  prices,
  consumption,
}: {
  status: EnergyStatus;
  prices: PricesResponse | undefined;
  consumption: ConsumptionNode[];
}) {
  const todayDate = new Date().toDateString();
  const todayEntries = consumption.filter(
    (n) => n.from && new Date(n.from).toDateString() === todayDate
  );
  const todayCost = todayEntries.reduce((s, n) => s + (n.cost ?? 0), 0);
  const todayKwh = todayEntries.reduce((s, n) => s + (n.consumption ?? 0), 0);
  const avgPrice =
    prices?.today && prices.today.length > 0
      ? prices.today.reduce((s, e) => s + e.total, 0) / prices.today.length
      : null;

  const cards = [
    { label: "Today's cost", value: `kr ${todayCost.toFixed(2)}` },
    { label: "Today's usage", value: `${todayKwh.toFixed(2)} kWh` },
    {
      label: "Current power",
      value:
        status.current_power != null
          ? `${Math.round(status.current_power)} W`
          : "—",
      muted: status.current_power == null,
    },
    {
      label: "Avg price today",
      value: avgPrice != null ? `${(avgPrice * 100).toFixed(1)} øre/kWh` : "—",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cards.map(({ label, value, muted }) => (
        <div
          key={label}
          className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-navy-800/60"
        >
          <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
          <div
            className={`mt-1 text-xl font-bold tabular-nums ${
              muted
                ? "text-slate-400 dark:text-slate-500"
                : "text-slate-900 dark:text-white"
            }`}
          >
            {value}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PowerHistoryPanel
// ---------------------------------------------------------------------------

function PowerHistoryPanel({ enabled }: { enabled: boolean }) {
  const [range, setRange] = useState<HistoryRange>("1h");
  const { lightMode } = useUISettings();

  const { data: powerHistory = [], isLoading } = useQuery({
    queryKey: ["energy-power", range],
    queryFn: () => getEnergyHistoryPower(range),
    staleTime: 30_000,
    enabled,
  });

  const gridColor = lightMode ? "rgba(0,0,0,0.07)" : "rgba(255,255,255,0.06)";
  const axisColor = lightMode ? "rgba(0,0,0,0.45)" : "rgba(255,255,255,0.3)";
  const tooltipStyle = lightMode
    ? { backgroundColor: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, color: "#0f172a", fontSize: 12 }
    : { backgroundColor: "#1e293b", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, color: "#f8fafc", fontSize: 12 };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Power history</h2>
        <RangeSelector value={range} onChange={setRange} />
      </div>

      {isLoading ? (
        <div className="flex h-[200px] items-center justify-center">
          <div className="h-7 w-7 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
        </div>
      ) : powerHistory.length === 0 ? (
        <div className="flex h-[200px] items-center justify-center">
          <p className="text-sm text-slate-400 dark:text-slate-500">No data for this period.</p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={powerHistory as PowerPoint[]} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={gridColor} strokeDasharray="3 3" />
            <XAxis
              dataKey="time"
              tickFormatter={(v) => formatTime(v as string, range)}
              tick={{ fill: axisColor, fontSize: 11 }}
              axisLine={{ stroke: gridColor }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: axisColor, fontSize: 11 }}
              axisLine={{ stroke: gridColor }}
              tickLine={false}
              unit=" W"
              width={52}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(v) => formatTime(v as string, range)}
              formatter={(value: number) => [`${Math.round(value)} W`, "Power"]}
            />
            <Line
              type="monotone"
              dataKey="power"
              stroke="#38bdf8"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: "#38bdf8" }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PhaseHistoryPanel
// ---------------------------------------------------------------------------

const PHASE_COLORS = ["#f97316", "#a78bfa", "#34d399"];

const PHASE_CONFIG = {
  voltage: {
    keys: ["voltagePhase1", "voltagePhase2", "voltagePhase3"] as const,
    labels: ["L1 (V)", "L2 (V)", "L3 (V)"],
    unit: " V" as const,
    yWidth: 52,
    decimals: 1,
  },
  current: {
    keys: ["currentL1", "currentL2", "currentL3"] as const,
    labels: ["L1 (A)", "L2 (A)", "L3 (A)"],
    unit: " A" as const,
    yWidth: 44,
    decimals: 2,
  },
};

function PhaseHistoryPanel({
  type,
  title,
  enabled,
}: {
  type: "voltage" | "current";
  title: string;
  enabled: boolean;
}) {
  const [range, setRange] = useState<HistoryRange>("1h");
  const { lightMode } = useUISettings();
  const cfg = PHASE_CONFIG[type];

  const { data: phases = [], isLoading } = useQuery({
    queryKey: ["energy-phases", range],
    queryFn: () => getEnergyHistoryPhases(range),
    staleTime: 30_000,
    enabled,
  });

  const gridColor = lightMode ? "rgba(0,0,0,0.07)" : "rgba(255,255,255,0.06)";
  const axisColor = lightMode ? "rgba(0,0,0,0.45)" : "rgba(255,255,255,0.3)";
  const tooltipStyle = lightMode
    ? { backgroundColor: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, color: "#0f172a", fontSize: 12 }
    : { backgroundColor: "#1e293b", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, color: "#f8fafc", fontSize: 12 };

  const hasData = phases.length > 0 && phases.some((p) =>
    cfg.keys.some((k) => p[k as keyof PhasePoint] != null)
  );

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">{title}</h2>
          <div className="flex gap-3">
            {PHASE_COLORS.map((c, i) => (
              <span key={i} className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                <span className="inline-block h-2 w-4 rounded-sm" style={{ backgroundColor: c }} />
                {`L${i + 1}`}
              </span>
            ))}
          </div>
        </div>
        <RangeSelector value={range} onChange={setRange} />
      </div>

      {isLoading ? (
        <div className="flex h-[200px] items-center justify-center">
          <div className="h-7 w-7 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
        </div>
      ) : !hasData ? (
        <div className="flex h-[200px] items-center justify-center">
          <p className="text-sm text-slate-400 dark:text-slate-500">No data for this period.</p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={phases as PhasePoint[]} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={gridColor} strokeDasharray="3 3" />
            <XAxis
              dataKey="time"
              tickFormatter={(v) => formatTime(v as string, range)}
              tick={{ fill: axisColor, fontSize: 11 }}
              axisLine={{ stroke: gridColor }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: axisColor, fontSize: 11 }}
              axisLine={{ stroke: gridColor }}
              tickLine={false}
              unit={cfg.unit}
              width={cfg.yWidth}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(v) => formatTime(v as string, range)}
              formatter={(value: number, name: string) => {
                const idx = (cfg.keys as readonly string[]).indexOf(name);
                return [`${value.toFixed(cfg.decimals)}${cfg.unit}`, cfg.labels[idx] ?? name];
              }}
            />
            {cfg.keys.map((k, i) => (
              <Line
                key={k}
                type="monotone"
                dataKey={k}
                stroke={PHASE_COLORS[i]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: PHASE_COLORS[i] }}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EnergyView
// ---------------------------------------------------------------------------

export default function EnergyView() {
  const queryClient = useQueryClient();

  const { data: status, isLoading } = useQuery({
    queryKey: ["energy-status"],
    queryFn: getEnergyStatus,
    refetchInterval: () => (document.hidden ? false : 2000),
  });

  const { data: prices } = useQuery({
    queryKey: ["energy-prices"],
    queryFn: getEnergyPrices,
    staleTime: msUntilMidnight(),
    enabled: status?.configured === true,
  });

  const { data: consumption = [] } = useQuery({
    queryKey: ["energy-consumption"],
    queryFn: () => getEnergyConsumption("HOURLY", 24),
    staleTime: 15 * 60 * 1000,
    enabled: status?.configured === true,
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-6">
        <Spinner />
      </div>
    );
  }

  if (!status?.configured) {
    return (
      <div className="mx-auto max-w-xl px-4 py-12">
        <SetupCard
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ["energy-status"] });
          }}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 space-y-6">
      <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Energy</h1>
      <StatusBar status={status} />
      {prices && <PriceChartSection prices={prices} />}
      <StatsCards status={status} prices={prices} consumption={consumption} />
      <PowerHistoryPanel enabled={status.configured} />
      <PhaseHistoryPanel type="current" title="Current" enabled={status.configured} />
      <PhaseHistoryPanel type="voltage" title="Voltage" enabled={status.configured} />
    </div>
  );
}
