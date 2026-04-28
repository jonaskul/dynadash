import { Minus, Plus } from "lucide-react";

interface Props {
  setpoint: number | null;
  min: number;
  max: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}

const STEP = 0.5;

export default function TemperaturePicker({ setpoint, min, max, disabled = false, onChange }: Props) {
  function decrement() {
    const base = setpoint ?? min;
    const next = Math.max(min, Math.round((base - STEP) * 10) / 10);
    if (next !== setpoint) onChange(next);
  }

  function increment() {
    const base = setpoint ?? min;
    // If current setpoint is below the allowed minimum, jump straight to min
    if (base < min) { onChange(min); return; }
    const next = Math.min(max, Math.round((base + STEP) * 10) / 10);
    if (next !== setpoint) onChange(next);
  }

  const btnCls = "flex h-8 w-8 items-center justify-center rounded-full border transition-colors disabled:opacity-30 disabled:cursor-not-allowed border-slate-200 bg-slate-50 text-slate-500 hover:border-electric-blue/50 hover:text-slate-800 dark:border-white/15 dark:bg-white/5 dark:text-slate-300 dark:hover:border-electric-blue/50 dark:hover:text-white";

  return (
    <div className="flex items-center gap-3">
      <button onClick={decrement} disabled={disabled || (setpoint !== null && setpoint <= min)} className={btnCls}>
        <Minus className="h-4 w-4" />
      </button>

      <div className="flex min-w-[4.5rem] flex-col items-center">
        <span className="text-xl font-bold tabular-nums text-slate-900 dark:text-white">
          {setpoint !== null ? `${setpoint.toFixed(1)}°C` : "--"}
        </span>
        <span className="text-xs text-slate-400 dark:text-slate-500">setpoint</span>
      </div>

      <button onClick={increment} disabled={disabled || (setpoint !== null && setpoint >= max)} className={btnCls}>
        <Plus className="h-4 w-4" />
      </button>
    </div>
  );
}
