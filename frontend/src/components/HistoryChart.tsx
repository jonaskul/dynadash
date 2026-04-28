import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LevelPoint, TemperaturePoint } from "../api/types";
import { useUISettings } from "../context/UISettings";

function formatTime(iso: string, use24h: boolean): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: !use24h });
}

// ---------------------------------------------------------------------------
// Temperature chart
// ---------------------------------------------------------------------------

interface TempChartProps {
  data: TemperaturePoint[];
}

export function TemperatureChart({ data }: TempChartProps) {
  const { use24h, lightMode } = useUISettings();
  const gridColor = lightMode ? "rgba(0,0,0,0.07)" : "rgba(255,255,255,0.06)";
  const axisColor = lightMode ? "rgba(0,0,0,0.45)" : "rgba(255,255,255,0.3)";
  const tooltipStyle = lightMode
    ? { backgroundColor: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, color: "#0f172a", fontSize: 12 }
    : { backgroundColor: "#1e293b", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, color: "#f8fafc", fontSize: 12 };

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={gridColor} strokeDasharray="3 3" />
        <XAxis
          dataKey="time"
          tickFormatter={(v) => formatTime(v as string, use24h)}
          tick={{ fill: axisColor, fontSize: 11 }}
          axisLine={{ stroke: gridColor }}
          tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: axisColor, fontSize: 11 }}
          axisLine={{ stroke: gridColor }}
          tickLine={false}
          unit="°"
          domain={["auto", "auto"]}
          width={36}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(v) => formatTime(v as string, use24h)}
          formatter={(value: number, name: string) => [
            `${value.toFixed(1)}°C`,
            name === "temperature" ? "Temperature" : "Setpoint",
          ]}
        />
        <Legend
          wrapperStyle={{ color: axisColor, fontSize: 12 }}
          formatter={(value) => (value === "temperature" ? "Temperature" : "Setpoint")}
        />
        <Line
          type="monotone"
          dataKey="temperature"
          stroke="#38bdf8"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: "#38bdf8" }}
        />
        <Line
          type="monotone"
          dataKey="setpoint"
          stroke="#fbbf24"
          strokeWidth={1.5}
          strokeDasharray="5 3"
          dot={false}
          activeDot={{ r: 3, fill: "#fbbf24" }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Mini temperature sparkline (for use inside thermostat cards)
// ---------------------------------------------------------------------------

export function MiniTemperatureChart({ data }: TempChartProps) {
  const { use24h, lightMode } = useUISettings();
  const tooltipStyle = lightMode
    ? { background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 11 }
    : { background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, fontSize: 11 };

  return (
    <ResponsiveContainer width="100%" height={80}>
      <LineChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(v) => formatTime(v as string, use24h)}
          formatter={(value: number, name: string) => [
            `${value.toFixed(1)} °C`,
            name === "temperature" ? "Temp" : "Setpoint",
          ]}
        />
        <Line type="monotone" dataKey="temperature" stroke="#38bdf8" strokeWidth={1.5} dot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="setpoint" stroke="#fbbf24" strokeWidth={1} strokeDasharray="4 2" dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Level (lighting) chart
// ---------------------------------------------------------------------------

interface LevelChartProps {
  data: LevelPoint[];
}

export function LevelChart({ data }: LevelChartProps) {
  const { use24h, lightMode } = useUISettings();
  const gridColor = lightMode ? "rgba(0,0,0,0.07)" : "rgba(255,255,255,0.06)";
  const axisColor = lightMode ? "rgba(0,0,0,0.45)" : "rgba(255,255,255,0.3)";
  const tooltipStyle = lightMode
    ? { backgroundColor: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, color: "#0f172a", fontSize: 12 }
    : { backgroundColor: "#1e293b", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, color: "#f8fafc", fontSize: 12 };

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="levelGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={gridColor} strokeDasharray="3 3" />
        <XAxis
          dataKey="time"
          tickFormatter={(v) => formatTime(v as string, use24h)}
          tick={{ fill: axisColor, fontSize: 11 }}
          axisLine={{ stroke: gridColor }}
          tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: axisColor, fontSize: 11 }}
          axisLine={{ stroke: gridColor }}
          tickLine={false}
          unit="%"
          domain={[0, 100]}
          width={36}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(v) => formatTime(v as string, use24h)}
          formatter={(value: number) => [`${value.toFixed(0)}%`, "Level"]}
        />
        <Area
          type="stepAfter"
          dataKey="level"
          stroke="#38bdf8"
          strokeWidth={2}
          fill="url(#levelGradient)"
          dot={false}
          activeDot={{ r: 4, fill: "#38bdf8" }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
