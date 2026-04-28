import { Thermometer } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getTemperatureHistory, setSetpoint } from "../api/client";
import type { ThermostatAreaState } from "../api/types";
import { useClockFormat } from "../context/UISettings";
import TemperaturePicker from "./TemperaturePicker";
import { MiniTemperatureChart } from "./HistoryChart";

interface Props {
  area: ThermostatAreaState;
  onUpdated: () => void;
}

function tempColor(current: number | null, setpoint: number | null): string {
  if (current === null) return "text-slate-400";
  const ref = setpoint ?? 21;
  if (current < ref - 2) return "text-blue-500 dark:text-blue-400";
  if (current > ref + 2) return "text-orange-500 dark:text-orange-400";
  return "text-green-600 dark:text-green-400";
}

function tempGradientClass(current: number | null, setpoint: number | null): string {
  if (current === null) return "from-slate-100 to-slate-50 dark:from-slate-700 dark:to-slate-600";
  const ref = setpoint ?? 21;
  if (current < ref - 2) return "from-blue-50 to-blue-50/50 dark:from-blue-900/40 dark:to-blue-800/20";
  if (current > ref + 2) return "from-orange-50 to-orange-50/50 dark:from-orange-900/40 dark:to-orange-800/20";
  return "from-green-50 to-green-50/50 dark:from-green-900/40 dark:to-green-800/20";
}

export default function ThermostatCard({ area, onUpdated }: Props) {
  const [lastUpdated] = useState(() => new Date());
  const [pendingSetpoint, setPendingSetpoint] = useState<number | null>(null);
  const formatTime = useClockFormat();

  const { data: sparkData = [] } = useQuery({
    queryKey: ["spark-temp", area.id],
    queryFn: () => getTemperatureHistory(area.id, "24h"),
    staleTime: 5 * 60 * 1000,
  });
  const stale = !area.gateway_reachable;

  const displaySetpoint = pendingSetpoint ?? area.setpoint ?? null;

  async function handleSetpointChange(value: number) {
    setPendingSetpoint(value);
    try {
      await setSetpoint(area.id, value);
      onUpdated();
    } catch (err) {
      console.error("setSetpoint failed:", err);
      setPendingSetpoint(null);
    }
  }

  const colorClass = tempColor(area.current_temp, area.setpoint);
  const gradientClass = tempGradientClass(area.current_temp, area.setpoint);

  const presetLabel = area.current_preset !== null
    ? (area.presets[String(area.current_preset)] ?? `Preset ${area.current_preset}`)
    : null;

  const isActive = area.current_preset !== null && area.current_preset !== 0;
  const consumption = area.watts > 0 && isActive ? area.watts : 0;

  return (
    <div
      className={`
        rounded-xl border border-slate-200 bg-gradient-to-br ${gradientClass}
        p-5 transition-opacity duration-300 animate-fade-in
        bg-white dark:border-white/10 dark:backdrop-blur-sm dark:bg-navy-800/60
        ${stale ? "opacity-60" : ""}
      `}
    >
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Thermometer className={`h-5 w-5 ${colorClass}`} />
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">{area.name}</h2>
        </div>
        <div className="flex items-center gap-2">
          {presetLabel && (
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              isActive
                ? "bg-electric-blue/20 text-electric-blue"
                : "bg-slate-100 text-slate-500 dark:bg-white/5 dark:text-slate-500"
            }`}>
              {presetLabel}
            </span>
          )}
          {stale && (
            <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-600 dark:text-amber-400">
              stale
            </span>
          )}
        </div>
      </div>

      {/* Temperature display */}
      <div className="mb-5 flex items-end justify-center gap-1 py-2">
        <span className={`text-5xl font-bold tabular-nums ${colorClass}`}>
          {area.current_temp !== null ? area.current_temp.toFixed(1) : "--.-"}
        </span>
        <span className={`mb-2 text-2xl font-medium ${colorClass}`}>°C</span>
      </div>

      {/* Setpoint control */}
      <div className="flex justify-center">
        <TemperaturePicker
          setpoint={displaySetpoint}
          min={area.temp_min}
          max={area.temp_max}
          onChange={handleSetpointChange}
        />
      </div>

      {/* Sparkline */}
      <div className="mt-4 -mx-1">
        {sparkData.length > 0
          ? <MiniTemperatureChart data={sparkData} />
          : <div className="h-[80px] rounded bg-slate-100 animate-pulse dark:bg-white/5" />
        }
      </div>

      {/* Footer */}
      <div className="mt-3 flex items-center justify-between">
        {consumption > 0
          ? <span className="text-xs text-slate-400 dark:text-slate-500">{consumption} W</span>
          : <span />
        }
        <p className="text-xs text-slate-400 dark:text-slate-600">Updated {formatTime(lastUpdated)}</p>
      </div>
    </div>
  );
}
