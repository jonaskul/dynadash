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

// ---------------------------------------------------------------------------
// Shared chart styling
// ---------------------------------------------------------------------------

const GRID_COLOR = "rgba(255,255,255,0.06)";
const AXIS_COLOR = "rgba(255,255,255,0.3)";

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const tooltipStyle = {
  backgroundColor: "#1e293b",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 8,
  color: "#f8fafc",
  fontSize: 12,
};

// ---------------------------------------------------------------------------
// Temperature chart
// ---------------------------------------------------------------------------

interface TempChartProps {
  data: TemperaturePoint[];
}

export function TemperatureChart({ data }: TempChartProps) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
        <XAxis
          dataKey="time"
          tickFormatter={formatTime}
          tick={{ fill: AXIS_COLOR, fontSize: 11 }}
          axisLine={{ stroke: GRID_COLOR }}
          tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: AXIS_COLOR, fontSize: 11 }}
          axisLine={{ stroke: GRID_COLOR }}
          tickLine={false}
          unit="°"
          domain={["auto", "auto"]}
          width={36}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(v) => formatTime(v as string)}
          formatter={(value: number, name: string) => [
            `${value.toFixed(1)}°C`,
            name === "temperature" ? "Temperature" : "Setpoint",
          ]}
        />
        <Legend
          wrapperStyle={{ color: AXIS_COLOR, fontSize: 12 }}
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
// Level (lighting) chart
// ---------------------------------------------------------------------------

interface LevelChartProps {
  data: LevelPoint[];
}

export function LevelChart({ data }: LevelChartProps) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="levelGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
        <XAxis
          dataKey="time"
          tickFormatter={formatTime}
          tick={{ fill: AXIS_COLOR, fontSize: 11 }}
          axisLine={{ stroke: GRID_COLOR }}
          tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: AXIS_COLOR, fontSize: 11 }}
          axisLine={{ stroke: GRID_COLOR }}
          tickLine={false}
          unit="%"
          domain={[0, 100]}
          width={36}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(v) => formatTime(v as string)}
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
