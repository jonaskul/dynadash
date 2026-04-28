import { AlertTriangle } from "lucide-react";

interface Props {
  message?: string;
}

export default function StatusBanner({
  message = "Gateway unreachable — showing last known state",
}: Props) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-amber-400/40 bg-amber-50 px-4 py-3 text-amber-700 animate-fade-in dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400">
      <AlertTriangle className="h-5 w-5 shrink-0" />
      <p className="text-sm font-medium">{message}</p>
    </div>
  );
}
