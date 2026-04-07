import { Lightbulb, PowerOff } from "lucide-react";
import { useState } from "react";
import { setLevel, setPreset } from "../api/client";
import type { LightingAreaState } from "../api/types";
import LevelSlider from "./LevelSlider";
import PresetButton from "./PresetButton";

interface Props {
  area: LightingAreaState;
  onUpdated: () => void;
}

const OFF_PRESET = 65520;

function formatTime(date: Date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function LightingCard({ area, onUpdated }: Props) {
  const [lastUpdated] = useState(() => new Date());
  const [busy, setBusy] = useState(false);
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

  // Build channel state map for quick lookup
  const channelMap = new Map(area.channels.map((c) => [c.channel, c.level]));

  return (
    <div
      className={`
        rounded-xl border border-white/10 bg-navy-800/60 p-5 backdrop-blur-sm
        transition-opacity duration-300 animate-fade-in
        ${stale ? "opacity-60" : ""}
      `}
    >
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Lightbulb className="h-5 w-5 text-amber-400" />
          <h2 className="text-base font-semibold text-white">{area.name}</h2>
        </div>
        {stale && (
          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-400">
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
            className="flex items-center gap-1 rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm font-medium text-slate-400 transition-all hover:border-red-500/50 hover:text-red-400 disabled:opacity-40 disabled:cursor-not-allowed"
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
      <p className="mt-4 text-right text-xs text-slate-600">
        Updated {formatTime(lastUpdated)}
      </p>
    </div>
  );
}
