import { Thermometer } from "lucide-react";
import { useState } from "react";
import { setSetpoint } from "../api/client";
import type { ThermostatAreaState } from "../api/types";
import TemperaturePicker from "./TemperaturePicker";

interface Props {
  area: ThermostatAreaState;
  onUpdated: () => void;
}

function tempColor(current: number | null, setpoint: number | null): string {
  if (current === null) return "text-slate-400";
  const ref = setpoint ?? 21;
  if (current < ref - 2) return "text-blue-400";
  if (current > ref + 2) return "text-orange-400";
  return "text-green-400";
}

function tempGradientClass(current: number | null): string {
  if (current === null) return "from-slate-700 to-slate-600";
  if (current < 18) return "from-blue-900/40 to-blue-800/20";
  if (current > 24) return "from-orange-900/40 to-orange-800/20";
  return "from-green-900/40 to-green-800/20";
}

function formatTime(date: Date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function ThermostatCard({ area, onUpdated }: Props) {
  const [lastUpdated] = useState(() => new Date());
  const [pendingSetpoint, setPendingSetpoint] = useState<number | null>(null);
  const stale = !area.gateway_reachable;

  const displaySetpoint = pendingSetpoint ?? area.setpoint ?? area.temp_min;

  async function handleSetpointChange(value: number) {
    setPendingSetpoint(value);
    try {
      await setSetpoint(area.id, value);
      onUpdated();
    } catch {
      // revert on error
      setPendingSetpoint(null);
    }
  }

  const colorClass = tempColor(area.current_temp, area.setpoint);
  const gradientClass = tempGradientClass(area.current_temp);

  return (
    <div
      className={`
        rounded-xl border border-white/10 bg-gradient-to-br ${gradientClass}
        p-5 backdrop-blur-sm transition-opacity duration-300 animate-fade-in
        bg-navy-800/60
        ${stale ? "opacity-60" : ""}
      `}
    >
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Thermometer className={`h-5 w-5 ${colorClass}`} />
          <h2 className="text-base font-semibold text-white">{area.name}</h2>
        </div>
        {stale && (
          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-400">
            stale
          </span>
        )}
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
          disabled={stale}
          onChange={handleSetpointChange}
        />
      </div>

      {/* Footer */}
      <p className="mt-4 text-right text-xs text-slate-600">
        Updated {formatTime(lastUpdated)}
      </p>
    </div>
  );
}
