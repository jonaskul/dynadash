import { Minus, Plus } from "lucide-react";

interface Props {
  setpoint: number;
  min: number;
  max: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}

const STEP = 0.5;

export default function TemperaturePicker({ setpoint, min, max, disabled = false, onChange }: Props) {
  function decrement() {
    const next = Math.max(min, Math.round((setpoint - STEP) * 10) / 10);
    if (next !== setpoint) onChange(next);
  }

  function increment() {
    const next = Math.min(max, Math.round((setpoint + STEP) * 10) / 10);
    if (next !== setpoint) onChange(next);
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={decrement}
        disabled={disabled || setpoint <= min}
        className="flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-white/5 text-slate-300 transition-colors hover:border-electric-blue/50 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
      >
        <Minus className="h-4 w-4" />
      </button>

      <div className="flex min-w-[4.5rem] flex-col items-center">
        <span className="text-xl font-bold text-white tabular-nums">
          {setpoint.toFixed(1)}°C
        </span>
        <span className="text-xs text-slate-500">setpoint</span>
      </div>

      <button
        onClick={increment}
        disabled={disabled || setpoint >= max}
        className="flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-white/5 text-slate-300 transition-colors hover:border-electric-blue/50 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  );
}
