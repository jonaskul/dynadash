import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Download, Loader2, Moon, Sun, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { deleteGateway, getAppSettings, getGateway, importBackup, saveAppSettings, saveGateway, testGateway } from "../api/client";
import { useUISettings } from "../context/UISettings";

declare const __BUILD_TIME__: string;

function buildVersion(): string {
  try {
    const d = new Date(__BUILD_TIME__);
    const pad = (n: number) => String(n).padStart(2, "0");
    return (
      `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
      `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`
    );
  } catch {
    return "unknown";
  }
}

type TestResult = { success: boolean; message: string; url: string };

interface EditFormProps {
  ip: string; setIp: (v: string) => void;
  https: boolean; setHttps: (v: boolean) => void;
  verifySSL: boolean; setVerifySSL: (v: boolean) => void;
  useAuth: boolean; setUseAuth: (v: boolean) => void;
  username: string; setUsername: (v: string) => void;
  password: string; setPassword: (v: string) => void;
  testResult: TestResult | null;
  error: string | null;
  testing: boolean; saving: boolean;
  onTest: () => void; onSave: () => void;
  onCancel?: () => void;
  showCancel?: boolean;
}

const inputCls = "w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none transition focus:border-electric-blue/60 focus:ring-1 focus:ring-electric-blue/30 dark:border-white/15 dark:bg-white/5 dark:text-white dark:placeholder-slate-500";

function EditForm({
  ip, setIp, https, setHttps, verifySSL, setVerifySSL,
  useAuth, setUseAuth, username, setUsername, password, setPassword,
  testResult, error, testing, saving, onTest, onSave, onCancel, showCancel,
}: EditFormProps) {
  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">IP Address</label>
        <input type="text" className={inputCls} value={ip}
          onChange={(e) => setIp(e.target.value)} placeholder="192.168.1.50" />
      </div>
      <Checkbox checked={https} onChange={setHttps} label="Use HTTPS" />
      <Checkbox checked={!verifySSL} onChange={(v) => setVerifySSL(!v)}
        disabled={!https} label="Ignore certificate errors" />
      <Checkbox checked={useAuth} onChange={setUseAuth} label="Require authentication" />
      {useAuth && (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-white/10 dark:bg-white/5">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Username</label>
            <input type="text" className={inputCls} value={username}
              onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
              Password {showCancel && <span className="text-slate-400 dark:text-slate-500">(leave blank to keep)</span>}
            </label>
            <input type="password" className={inputCls} value={password}
              onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
        </div>
      )}
      {testResult && <TerminalResult result={testResult} />}
      {error && <p className="text-sm text-red-500 dark:text-red-400">{error}</p>}
      <div className="flex gap-3">
        <button onClick={onTest} disabled={testing || !ip}
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 transition disabled:opacity-40 dark:border-white/15 dark:bg-white/5 dark:text-slate-300 dark:hover:text-white">
          {testing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Test
        </button>
        <button onClick={onSave} disabled={saving || !ip}
          className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-electric-blue py-2 text-sm font-semibold text-navy-900 hover:bg-electric-blue-light transition disabled:opacity-40">
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Save
        </button>
        {showCancel && onCancel && (
          <button onClick={onCancel}
            className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-600 hover:text-slate-900 transition dark:border-white/15 dark:bg-white/5 dark:text-slate-300 dark:hover:text-white">
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

function TerminalResult({ result }: { result: TestResult }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-100 p-3 font-mono text-xs space-y-1 dark:border-white/10 dark:bg-black/60">
      <div className="text-slate-500 break-all dark:text-slate-400">
        <span className="text-green-600 dark:text-green-400">$</span> GET {result.url}
      </div>
      <div className={result.success ? "text-green-600 dark:text-green-400" : "text-red-500 dark:text-red-400"}>
        <span className="text-slate-400 dark:text-slate-500">&gt;</span> {result.message}
      </div>
    </div>
  );
}

function Checkbox({ checked, onChange, disabled, label }: {
  checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label: string;
}) {
  return (
    <label className={`flex items-center gap-2.5 select-none ${disabled ? "cursor-not-allowed opacity-40" : "cursor-pointer"}`}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        disabled={disabled} className="h-4 w-4 rounded border-slate-300 bg-white accent-electric-blue dark:border-white/20 dark:bg-white/5" />
      <span className="text-sm text-slate-600 dark:text-slate-300">{label}</span>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Appearance section
// ---------------------------------------------------------------------------

function AppearanceSection() {
  const { use24h, setUse24h, lightMode, setLightMode } = useUISettings();

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-5 dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm">
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Appearance</h2>

      {/* Theme toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          {lightMode
            ? <Sun className="h-4 w-4 text-amber-500" />
            : <Moon className="h-4 w-4 text-slate-400" />}
          <div>
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
              {lightMode ? "Light mode" : "Dark mode"}
            </p>
            <p className="text-xs text-slate-500">Toggle between light and dark interface</p>
          </div>
        </div>
        <Toggle checked={lightMode} onChange={setLightMode} />
      </div>

      <div className="border-t border-slate-100 dark:border-white/5" />

      {/* 24h clock toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Clock className="h-4 w-4 text-slate-400" />
          <div>
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200">24-hour clock</p>
            <p className="text-xs text-slate-500">
              {use24h ? "Showing 14:30" : "Showing 2:30 PM"}
            </p>
          </div>
        </div>
        <Toggle checked={use24h} onChange={setUse24h} />
      </div>
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-electric-blue ${
        checked ? "bg-electric-blue" : "bg-slate-300 dark:bg-slate-600"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Backup section
// ---------------------------------------------------------------------------

type ExportRange = "7d" | "30d" | "90d" | "all";

const EXPORT_RANGES: { value: ExportRange; label: string }[] = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "all", label: "All time" },
];

const selectCls = "rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-electric-blue/60 focus:ring-1 focus:ring-electric-blue/30 dark:border-white/15 dark:bg-white/5 dark:text-slate-300";

function BackupSection() {
  const [range, setRange] = useState<ExportRange>("7d");
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleExport() {
    setExporting(true);
    setMessage(null);
    setError(null);
    try {
      const res = await fetch(`/api/backup/export?range=${range}`);
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dynadash-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String(e));
    } finally {
      setExporting(false);
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setMessage(null);
    setError(null);
    try {
      const data = JSON.parse(await file.text());
      const result = await importBackup(data);
      const pts = result.temperature_points + result.level_points;
      setMessage(`Imported ${result.areas_imported} areas and ${pts} history points.`);
    } catch (e) {
      setError(String(e));
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-4 dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm">
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Import / Export</h2>

      {/* Export */}
      <div>
        <p className="mb-2 text-xs text-slate-500">Download a backup of all areas and history data.</p>
        <div className="flex items-center gap-2">
          <select
            value={range}
            onChange={(e) => setRange(e.target.value as ExportRange)}
            className={selectCls}
          >
            {EXPORT_RANGES.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-2 rounded-lg bg-electric-blue px-4 py-2 text-sm font-semibold text-navy-900 hover:bg-electric-blue-light transition disabled:opacity-40"
          >
            {exporting
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <Download className="h-4 w-4" />}
            Export
          </button>
        </div>
      </div>

      <div className="border-t border-slate-100 dark:border-white/5" />

      {/* Import */}
      <div>
        <p className="mb-2 text-xs text-slate-500">Restore from a backup file. Replaces all areas and merges history.</p>
        <input
          ref={fileRef}
          type="file"
          accept=".json"
          onChange={handleImport}
          className="hidden"
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={importing}
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition disabled:opacity-40 dark:border-white/15 dark:bg-white/5 dark:text-slate-300 dark:hover:text-white dark:hover:bg-white/10"
        >
          {importing
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <Upload className="h-4 w-4" />}
          Import backup
        </button>
      </div>

      {message && <p className="text-xs text-green-600 dark:text-green-400">{message}</p>}
      {error && <p className="text-xs text-red-500 dark:text-red-400">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main settings view
// ---------------------------------------------------------------------------

export default function SettingsView() {
  const queryClient = useQueryClient();

  const { data: gateway, isLoading } = useQuery({
    queryKey: ["gateway"],
    queryFn: getGateway,
    staleTime: 30_000,
  });

  const [ip, setIp] = useState("");
  const [https, setHttps] = useState(false);
  const [verifySSL, setVerifySSL] = useState(true);
  const [useAuth, setUseAuth] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [editing, setEditing] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scheme = https ? "https" : "http";

  function startEditing() {
    setIp(gateway?.ip ?? "");
    setHttps(gateway?.scheme === "https");
    setVerifySSL(gateway?.verify_ssl ?? true);
    setUseAuth(!!(gateway?.username));
    setUsername(gateway?.username ?? "");
    setPassword("");
    setTestResult(null);
    setError(null);
    setEditing(true);
  }

  async function handleTest() {
    if (!ip) return;
    setTesting(true);
    setTestResult(null);
    const url = `${scheme}://${ip}/GetDyNet.cgi?a=1&p=65535&j=255`;
    try {
      const result = await testGateway({ ip, scheme, verify_ssl: verifySSL,
        username: useAuth ? username : "", password: useAuth ? password : "" });
      setTestResult({ ...result, url });
    } catch (e) {
      setTestResult({ success: false, message: String(e), url });
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    if (!ip) { setError("IP address is required."); return; }
    setSaving(true);
    setError(null);
    try {
      await saveGateway({ ip, scheme, verify_ssl: verifySSL,
        username: useAuth ? username : "", password: useAuth ? password : "" });
      queryClient.invalidateQueries({ queryKey: ["gateway"] });
      setEditing(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    if (!confirm("Remove gateway configuration?")) return;
    try {
      await deleteGateway();
      queryClient.invalidateQueries({ queryKey: ["gateway"] });
    } catch (e) {
      setError(String(e));
    }
  }

  const editFormProps: Omit<EditFormProps, "showCancel" | "onCancel"> = {
    ip, setIp, https, setHttps, verifySSL, setVerifySSL,
    useAuth, setUseAuth, username, setUsername, password, setPassword,
    testResult, error, testing, saving,
    onTest: handleTest, onSave: handleSave,
  };

  return (
    <div className="mx-auto max-w-xl px-4 py-6 space-y-6">
      <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Settings</h1>

      {/* Appearance */}
      <AppearanceSection />

      {/* Gateway */}
      <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-5 dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Gateway Configuration</h2>

        {isLoading ? (
          <div className="flex h-16 items-center justify-center">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
          </div>
        ) : !gateway ? (
          <div className="space-y-4">
            <p className="text-sm text-slate-500 dark:text-slate-400">No gateway configured.</p>
            <EditForm {...editFormProps} />
          </div>
        ) : !editing ? (
          <div className="space-y-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2 dark:border-white/10 dark:bg-white/5">
              <div className="flex justify-between text-sm">
                <span className="text-slate-500 dark:text-slate-400">IP Address</span>
                <span className="font-mono text-slate-900 dark:text-white">{gateway.ip}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-500 dark:text-slate-400">Protocol</span>
                <span className="font-mono text-slate-900 dark:text-white">{gateway.scheme}</span>
              </div>
              {gateway.scheme === "https" && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500 dark:text-slate-400">Verify SSL</span>
                  <span className={`font-mono ${gateway.verify_ssl ? "text-green-600 dark:text-green-400" : "text-amber-500 dark:text-amber-400"}`}>
                    {gateway.verify_ssl ? "yes" : "no"}
                  </span>
                </div>
              )}
              {gateway.username && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500 dark:text-slate-400">Username</span>
                  <span className="font-mono text-slate-900 dark:text-white">{gateway.username}</span>
                </div>
              )}
            </div>
            <button onClick={startEditing}
              className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition dark:border-white/15 dark:bg-white/5 dark:text-slate-300 dark:hover:text-white dark:hover:bg-white/10">
              Edit
            </button>
          </div>
        ) : (
          <EditForm {...editFormProps} showCancel onCancel={() => setEditing(false)} />
        )}
      </div>

      {/* Import / Export */}
      <BackupSection />

      {/* Danger zone */}
      {gateway && !isLoading && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-5 space-y-3 dark:border-red-500/20 dark:bg-red-500/5">
          <h2 className="text-sm font-semibold text-red-600 dark:text-red-400">Danger Zone</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">Removes the gateway IP address from configuration.</p>
          <button onClick={handleReset}
            className="flex items-center gap-2 rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-100 transition dark:border-red-500/40 dark:text-red-400 dark:hover:bg-red-500/10">
            <Trash2 className="h-4 w-4" />
            Reset Gateway
          </button>
        </div>
      )}

      {/* Polling interval */}
      <PollingIntervalSection />

      {/* Version */}
      <div className="flex justify-end">
        <span className="text-xs font-mono text-slate-400 dark:text-slate-600">{buildVersion()}</span>
      </div>
    </div>
  );
}

function PollingIntervalSection() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["app-settings"],
    queryFn: getAppSettings,
    staleTime: 60_000,
  });

  const [value, setValue] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const current = value ?? data?.polling_interval_seconds ?? 10;

  async function handleSave() {
    setSaving(true);
    try {
      await saveAppSettings({ polling_interval_seconds: current });
      queryClient.invalidateQueries({ queryKey: ["app-settings"] });
      setValue(null);
    } finally {
      setSaving(false);
    }
  }

  const isDirty = value !== null && value !== data?.polling_interval_seconds;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-4 dark:border-white/10 dark:bg-navy-800/60 dark:backdrop-blur-sm">
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Polling Interval</h2>
      <p className="text-xs text-slate-500">
        How often to read state from all areas. Each area is polled 2 s apart to avoid
        overloading the gateway.
      </p>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500 dark:text-slate-400">Interval</span>
          <span className="text-sm font-mono font-medium text-slate-900 tabular-nums dark:text-white">
            {Math.round(current / 60)} min
          </span>
        </div>
        <input
          type="range"
          min={1}
          max={60}
          step={1}
          value={Math.round(current / 60)}
          onChange={(e) => setValue(Number(e.target.value) * 60)}
          className="w-full accent-electric-blue"
        />
        <div className="flex justify-between text-xs text-slate-400 dark:text-slate-600">
          <span>1 min</span>
          <span>60 min</span>
        </div>
      </div>

      {isDirty && (
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-electric-blue px-4 py-2 text-sm font-semibold text-navy-900 hover:bg-electric-blue-light transition disabled:opacity-40"
        >
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Save
        </button>
      )}
    </div>
  );
}
