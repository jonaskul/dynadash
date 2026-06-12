interface Props {
  label: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}

export default function PresetButton({ label, active, disabled = false, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`
        rounded-md px-3 py-1.5 text-sm font-medium transition-all duration-150
        ${
          active
            ? "bg-electric-blue text-navy-900 shadow-lg shadow-electric-blue/30"
            : "border border-slate-200 bg-slate-50 text-slate-600 hover:border-electric-blue/40 hover:text-slate-900 hover:bg-slate-100 dark:border-white/15 dark:bg-white/5 dark:text-slate-300 dark:hover:border-electric-blue/50 dark:hover:text-white dark:hover:bg-white/10"
        }
        disabled:opacity-40 disabled:cursor-not-allowed
      `}
    >
      {label}
    </button>
  );
}
