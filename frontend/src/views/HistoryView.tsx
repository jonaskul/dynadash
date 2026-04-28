import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  getConfigAreas,
  getLevelHistory,
  getTemperatureHistory,
} from "../api/client";
import { LevelChart, TemperatureChart } from "../components/HistoryChart";

const RANGES = ["1h", "6h", "24h", "7d"] as const;
type Range = (typeof RANGES)[number];

const selectCls = "rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-electric-blue/50 dark:border-white/15 dark:bg-navy-800 dark:text-white";

export default function HistoryView() {
  const [range, setRange] = useState<Range>("24h");
  const [selectedAreaId, setSelectedAreaId] = useState<number | null>(null);
  const [selectedChannel, setSelectedChannel] = useState(1);

  const { data: areas = [] } = useQuery({
    queryKey: ["config-areas"],
    queryFn: getConfigAreas,
    staleTime: 60_000,
  });

  const currentArea = areas.find((a) => a.id === selectedAreaId) ?? areas[0] ?? null;
  const effectiveAreaId = currentArea?.id ?? null;

  const { data: tempHistory = [], isLoading: loadingTemp } = useQuery({
    queryKey: ["history-temp", effectiveAreaId, range],
    queryFn: () => getTemperatureHistory(effectiveAreaId!, range),
    enabled: currentArea?.type === "thermostat" && effectiveAreaId !== null,
    staleTime: 30_000,
  });

  const { data: levelHistory = [], isLoading: loadingLevel } = useQuery({
    queryKey: ["history-level", effectiveAreaId, selectedChannel, range],
    queryFn: () => getLevelHistory(effectiveAreaId!, selectedChannel, range),
    enabled: currentArea?.type === "lighting" && effectiveAreaId !== null,
    staleTime: 30_000,
  });

  const isLoading = loadingTemp || loadingLevel;

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 space-y-6">
      <h1 className="text-xl font-semibold text-slate-900 dark:text-white">History</h1>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Area selector */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Area</label>
          <select
            value={effectiveAreaId ?? ""}
            onChange={(e) => {
              setSelectedAreaId(Number(e.target.value));
              setSelectedChannel(1);
            }}
            className={selectCls}
          >
            {areas.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </div>

        {/* Channel selector (lighting only) */}
        {currentArea?.type === "lighting" && currentArea.channels > 1 && (
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Channel</label>
            <select
              value={selectedChannel}
              onChange={(e) => setSelectedChannel(Number(e.target.value))}
              className={selectCls}
            >
              {Array.from({ length: currentArea.channels }, (_, i) => i + 1).map((ch) => (
                <option key={ch} value={ch}>
                  Channel {ch}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Range buttons */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Range</label>
          <div className="flex rounded-lg border border-slate-200 overflow-hidden dark:border-white/10">
            {RANGES.map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`px-3 py-2 text-sm font-medium transition-colors ${
                  range === r
                    ? "bg-electric-blue text-navy-900"
                    : "bg-white text-slate-500 hover:text-slate-900 hover:bg-slate-50 dark:bg-navy-800 dark:text-slate-400 dark:hover:text-white dark:hover:bg-white/5"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 min-h-[320px] flex items-center justify-center dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm">
        {areas.length === 0 ? (
          <p className="text-slate-400 dark:text-slate-500">No areas configured.</p>
        ) : isLoading ? (
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
        ) : currentArea?.type === "thermostat" ? (
          tempHistory.length === 0 ? (
            <p className="text-slate-400 dark:text-slate-500">No data for this period.</p>
          ) : (
            <div className="w-full">
              <p className="mb-3 text-sm font-medium text-slate-500 dark:text-slate-400">
                {currentArea.name} — Temperature ({range})
              </p>
              <TemperatureChart data={tempHistory} />
            </div>
          )
        ) : levelHistory.length === 0 ? (
          <p className="text-slate-400 dark:text-slate-500">No data for this period.</p>
        ) : (
          <div className="w-full">
            <p className="mb-3 text-sm font-medium text-slate-500 dark:text-slate-400">
              {currentArea?.name} — Channel {selectedChannel} Level ({range})
            </p>
            <LevelChart data={levelHistory} />
          </div>
        )}
      </div>
    </div>
  );
}
