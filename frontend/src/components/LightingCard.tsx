import { Lightbulb, PowerOff } from "lucide-react";
import { useState } from "react";
import { setLevel, setPreset } from "../api/client";
import type { LightingAreaState } from "../api/types";
import { useClockFormat } from "../context/UISettings";
import LevelSlider from "./LevelSlider";
import PresetButton from "./PresetButton";

interface Props {
  area: LightingAreaState;
  onUpdated: () => void;
}

const OFF_PRESET = 65520;

export default function LightingCard({ area, onUpdated }: Props) {
  const [lastUpdated] = useState(() => new Date());
  const [busy, setBusy] = useState(false);
  const formatTime = useClockFormat();
  const stale = !area.gateway_reachable;

  async function handlePreset(preset: number) {
    if (busy) return;
    setBusy(true);
    try {
      await setPreset(area.id, preset);
      onUpdated();
    } finally {
      setBusy(false);
    }
  }

  async function handleLevel(channel: number, level: number) {
    try {
      await setLevel(area.id, channel, level);
      onUpdated();
    } catch {
      // level slider errors are silent — next poll will restore correct state
    }
  }

  const presetEntries = Object.entries(area.presets).filter(
    ([key]) => key !== String(OFF_PRESET)
  );

  const channelMap = new Map(area.channels.map((c) => [c.channel, c.level]));

  return (
    <div
      className={`
        rounded-xl border border-slate-200 bg-white p-5
        dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm
        transition-opacity duration-300 animate-fade-in
        ${stale ? "opacity-60" : ""}
      `}
    >
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Lightbulb className="h-5 w-5 text-amber-500 dark:text-amber-400" />
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">{area.name}</h2>
        </div>
        {stale && (
          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-600 dark:text-amber-400">
            stale
          </span>
        )}
      </div>

      {/* Preset buttons */}
      {presetEntries.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {presetEntries.map(([key, label]) => (
            <PresetButton
              key={key}
              label={label}
              active={area.current_preset === Number(key)}
              disabled={busy || stale}
              onClick={() => handlePreset(Number(key))}
            />
          ))}
          <button
            onClick={() => handlePreset(OFF_PRESET)}
            disabled={busy || stale}
            className="flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-500 transition-all hover:border-red-300 hover:text-red-500 disabled:opacity-40 disabled:cursor-not-allowed dark:border-white/10 dark:bg-white/5 dark:text-slate-400 dark:hover:border-red-500/50 dark:hover:text-red-400"
          >
            <PowerOff className="h-3.5 w-3.5" />
            Off
          </button>
        </div>
      )}

      {/* Channel sliders */}
      <div className="space-y-3">
        {Array.from({ length: area.num_channels }, (_, i) => i + 1).map((ch) => (
          <LevelSlider
            key={ch}
            channel={ch}
            level={channelMap.get(ch) ?? 0}
            disabled={stale}
            onChange={handleLevel}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="mt-4 flex items-center justify-between">
        {area.watts > 0 ? (() => {
          const levels = Array.from({ length: area.num_channels }, (_, i) => channelMap.get(i + 1) ?? 0);
          const avg = levels.reduce((s, l) => s + l, 0) / levels.length;
          const w = Math.round(area.watts * avg / 100);
          return <span className="text-xs text-slate-400 dark:text-slate-500">{w} W</span>;
        })() : <span />}
        <p className="text-xs text-slate-400 dark:text-slate-600">Updated {formatTime(lastUpdated)}</p>
      </div>
    </div>
  );
}
