import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Zap } from "lucide-react";
import { getGateway } from "../api/client";
import { getAreas } from "../api/client";

function LiveClock() {
  const [time, setTime] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <span className="text-sm font-mono text-slate-400 tabular-nums">
      {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
    </span>
  );
}

function GatewayDot() {
  const { data: areas } = useQuery({
    queryKey: ["areas"],
    queryFn: getAreas,
    refetchInterval: 10_000,
    retry: false,
  });

  const reachable =
    Array.isArray(areas) && areas.length > 0 && areas[0].gateway_reachable;

  const { data: gw } = useQuery({
    queryKey: ["gateway"],
    queryFn: getGateway,
    staleTime: 60_000,
  });

  const isConfigured = gw !== null && gw !== undefined;

  const color = !isConfigured
    ? "bg-slate-500"
    : reachable
    ? "bg-green-400"
    : "bg-red-500";

  const label = !isConfigured
    ? "No gateway"
    : reachable
    ? "Gateway reachable"
    : "Gateway unreachable";

  return (
    <div className="flex items-center gap-1.5" title={label}>
      <span className={`h-2.5 w-2.5 rounded-full ${color} shadow-lg`} />
      <span className="hidden sm:inline text-xs text-slate-400">{label}</span>
    </div>
  );
}

const NAV_LINKS = [
  { to: "/", label: "Control" },
  { to: "/history", label: "History" },
  { to: "/areas", label: "Areas" },
  { to: "/settings", label: "Settings" },
];

export default function Navbar() {
  const location = useLocation();

  return (
    <nav className="sticky top-0 z-50 border-b border-white/10 bg-navy-900/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
        {/* Wordmark */}
        <Link to="/" className="flex items-center gap-2 select-none">
          <Zap className="h-5 w-5 text-electric-blue" fill="currentColor" />
          <span className="text-lg font-bold tracking-widest text-white">
            DYNA<span className="text-electric-blue">DASH</span>
          </span>
        </Link>

        {/* Nav links */}
        <div className="hidden sm:flex items-center gap-1">
          {NAV_LINKS.map(({ to, label }) => {
            const active = to === "/" ? location.pathname === "/" : location.pathname.startsWith(to);
            return (
              <Link
                key={to}
                to={to}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-electric-blue/20 text-electric-blue"
                    : "text-slate-400 hover:text-white hover:bg-white/5"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </div>

        {/* Right side */}
        <div className="flex items-center gap-4">
          <LiveClock />
          <GatewayDot />
        </div>
      </div>

      {/* Mobile nav */}
      <div className="sm:hidden flex border-t border-white/5 px-2 pb-2">
        {NAV_LINKS.map(({ to, label }) => {
          const active = to === "/" ? location.pathname === "/" : location.pathname.startsWith(to);
          return (
            <Link
              key={to}
              to={to}
              className={`flex-1 rounded-md py-1.5 text-center text-xs font-medium transition-colors ${
                active
                  ? "text-electric-blue"
                  : "text-slate-500 hover:text-white"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
