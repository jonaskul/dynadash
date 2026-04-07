import { AlertTriangle } from "lucide-react";

interface Props {
  message?: string;
}

export default function StatusBanner({
  message = "Gateway unreachable — showing last known state",
}: Props) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-amber-400 animate-fade-in">
      <AlertTriangle className="h-5 w-5 shrink-0" />
      <p className="text-sm font-medium">{message}</p>
    </div>
  );
}
