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
            : "border border-white/15 bg-white/5 text-slate-300 hover:border-electric-blue/50 hover:text-white hover:bg-white/10"
        }
        disabled:opacity-40 disabled:cursor-not-allowed
      `}
    >
      {label}
    </button>
  );
}
