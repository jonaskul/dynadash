import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  channel: number;
  level: number;
  disabled?: boolean;
  onChange: (channel: number, level: number) => void;
}

function useDebounce<T extends (...args: Parameters<T>) => void>(fn: T, delay: number): T {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  return useCallback(
    (...args: Parameters<T>) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => fn(...args), delay);
    },
    [fn, delay]
  ) as T;
}

export default function LevelSlider({ channel, level, disabled = false, onChange }: Props) {
  const [localLevel, setLocalLevel] = useState(level);

  useEffect(() => {
    setLocalLevel(level);
  }, [level]);

  const debouncedOnChange = useDebounce(onChange, 400);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = Number(e.target.value);
    setLocalLevel(val);
    debouncedOnChange(channel, val);
  }

  return (
    <div className="flex items-center gap-3">
      <span className="w-16 shrink-0 text-xs text-slate-400">CH {channel}</span>
      <input
        type="range"
        min={0}
        max={100}
        value={localLevel}
        disabled={disabled}
        onChange={handleChange}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-electric-blue disabled:cursor-not-allowed disabled:opacity-40"
      />
      <span className="w-10 shrink-0 text-right text-sm font-mono text-slate-300">
        {Math.round(localLevel)}%
      </span>
    </div>
  );
}
