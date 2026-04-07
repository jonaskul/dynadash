import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LayoutGrid, Plus } from "lucide-react";
import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getAreas, getGateway } from "../api/client";
import type { LightingAreaState, ThermostatAreaState } from "../api/types";
import LightingCard from "../components/LightingCard";
import StatusBanner from "../components/StatusBanner";
import ThermostatCard from "../components/ThermostatCard";

export default function ControlView() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: gateway, isLoading: gwLoading } = useQuery({
    queryKey: ["gateway"],
    queryFn: getGateway,
    staleTime: 30_000,
  });

  const {
    data: areas = [],
    isLoading: areasLoading,
    isError,
  } = useQuery({
    queryKey: ["areas"],
    queryFn: getAreas,
    refetchInterval: 10_000,
    retry: false,
    enabled: gateway !== undefined,
  });

  useEffect(() => {
    if (!gwLoading && (gateway === null || gateway === undefined)) {
      navigate("/setup");
    }
  }, [gateway, gwLoading, navigate]);

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["areas"] });
  }

  if (gwLoading || areasLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
      </div>
    );
  }

  const anyUnreachable = areas.length > 0 && !areas[0].gateway_reachable;

  if (areas.length === 0) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12">
        <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-white/10 py-16 text-center">
          <LayoutGrid className="h-10 w-10 text-slate-600" />
          <div>
            <p className="text-lg font-medium text-slate-300">No areas configured</p>
            <p className="mt-1 text-sm text-slate-500">
              Add your first area to start controlling your lights and HVAC.
            </p>
          </div>
          <Link
            to="/areas"
            className="flex items-center gap-2 rounded-lg bg-electric-blue px-5 py-2.5 text-sm font-semibold text-navy-900 hover:bg-electric-blue-light transition"
          >
            <Plus className="h-4 w-4" />
            Add Area
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 space-y-6">
      {(anyUnreachable || isError) && <StatusBanner />}

      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {areas.map((area) => {
          if (area.type === "lighting") {
            return (
              <LightingCard
                key={area.id}
                area={area as LightingAreaState}
                onUpdated={refresh}
              />
            );
          }
          return (
            <ThermostatCard
              key={area.id}
              area={area as ThermostatAreaState}
              onUpdated={refresh}
            />
          );
        })}
      </div>
    </div>
  );
}
