import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import {
  getConfigAreas,
  getLevelHistory,
  getTemperatureHistory,
} from "../api/client";
import type { AreaConfig } from "../api/types";
import { LevelChart, TemperatureChart } from "../components/HistoryChart";

const RANGES = ["1h", "6h", "24h", "7d"] as const;
type Range = (typeof RANGES)[number];

function sortAreas(areas: AreaConfig[]): AreaConfig[] {
  return [...areas].sort((a, b) => {
    if (a.order !== b.order) return a.order - b.order;
    return a.name.localeCompare(b.name);
  });
}

// ---------------------------------------------------------------------------
// Per-chart panels (each manages its own query)
// ---------------------------------------------------------------------------

function Spinner() {
  return (
    <div className="flex h-[200px] items-center justify-center">
      <div className="h-7 w-7 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
    </div>
  );
}

function Empty() {
  return (
    <div className="flex h-[200px] items-center justify-center">
      <p className="text-sm text-slate-400 dark:text-slate-500">No data for this period.</p>
    </div>
  );
}

function ThermostatChartPanel({ areaId, range }: { areaId: number; range: Range }) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["history-temp", areaId, range],
    queryFn: () => getTemperatureHistory(areaId, range),
    staleTime: 30_000,
  });

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm">
      {isLoading ? <Spinner /> : data.length === 0 ? <Empty /> : <TemperatureChart data={data} />}
    </div>
  );
}

function LightingChartPanel({
  areaId,
  channel,
  channels,
  range,
}: {
  areaId: number;
  channel: number;
  channels: number;
  range: Range;
}) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["history-level", areaId, channel, range],
    queryFn: () => getLevelHistory(areaId, channel, range),
    staleTime: 30_000,
  });

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm">
      {channels > 1 && (
        <p className="mb-3 text-xs font-medium text-slate-400 dark:text-slate-500">
          Channel {channel}
        </p>
      )}
      {isLoading ? <Spinner /> : data.length === 0 ? <Empty /> : <LevelChart data={data} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Area section
// ---------------------------------------------------------------------------

function AreaHistorySection({ area, range }: { area: AreaConfig; range: Range }) {
  const storageKey = `history-open-${area.id}`;
  const [open, setOpen] = useState(() => {
    const v = localStorage.getItem(storageKey);
    return v === null ? true : v === "true";
  });

  function toggle() {
    const next = !open;
    setOpen(next);
    localStorage.setItem(storageKey, String(next));
  }

  return (
    <section className="space-y-3">
      <button
        onClick={toggle}
        className="flex w-full items-center justify-between"
      >
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">{area.name}</h2>
        <ChevronDown
          className={`h-4 w-4 text-slate-400 transition-transform duration-200 ${open ? "" : "-rotate-90"}`}
        />
      </button>
      {open && (area.type === "thermostat" ? (
        <ThermostatChartPanel areaId={area.id} range={range} />
      ) : (
        <div className="space-y-3">
          {Array.from({ length: area.channels }, (_, i) => i + 1).map((ch) => (
            <LightingChartPanel
              key={ch}
              areaId={area.id}
              channel={ch}
              channels={area.channels}
              range={range}
            />
          ))}
        </div>
      ))}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main view
// ---------------------------------------------------------------------------

export default function HistoryView() {
  const [range, setRange] = useState<Range>("24h");

  const { data: areas = [], isLoading } = useQuery({
    queryKey: ["config-areas"],
    queryFn: getConfigAreas,
    staleTime: 60_000,
  });

  const sorted = sortAreas(areas);

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 space-y-6">
      {/* Header + range selector */}
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white">History</h1>
        <div className="flex rounded-lg border border-slate-200 overflow-hidden dark:border-white/10">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
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

      {/* Area charts */}
      {isLoading ? (
        <div className="flex h-32 items-center justify-center">
          <div className="h-7 w-7 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
        </div>
      ) : sorted.length === 0 ? (
        <p className="text-slate-500">No areas configured.</p>
      ) : (
        <div className="space-y-8">
          {sorted.map((area) => (
            <AreaHistorySection key={area.id} area={area} range={range} />
          ))}
        </div>
      )}
    </div>
  );
}
