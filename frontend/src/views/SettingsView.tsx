import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import { useState } from "react";
import { deleteGateway, getGateway, saveGateway, testGateway } from "../api/client";

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

function TerminalResult({ result }: { result: TestResult }) {
  return (
    <div className="rounded-lg bg-black/60 border border-white/10 p-3 font-mono text-xs space-y-1">
      <div className="text-slate-400 break-all">
        <span className="text-green-400">$</span> GET {result.url}
      </div>
      <div className={result.success ? "text-green-400" : "text-red-400"}>
        <span className="text-slate-500">&gt;</span> {result.message}
      </div>
    </div>
  );
}

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
      const result = await testGateway({ ip, scheme, verify_ssl: verifySSL });
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
      await saveGateway({ ip, scheme, verify_ssl: verifySSL });
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

  const inputCls = "w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2.5 text-sm text-white placeholder-slate-500 outline-none transition focus:border-electric-blue/60 focus:ring-1 focus:ring-electric-blue/30";

  return (
    <div className="mx-auto max-w-xl px-4 py-6 space-y-6">
      <h1 className="text-xl font-semibold text-white">Settings</h1>

      <div className="rounded-xl border border-white/10 bg-navy-800/60 p-6 backdrop-blur-sm space-y-5">
        <h2 className="text-sm font-semibold text-slate-300">Gateway Configuration</h2>

        {isLoading ? (
          <div className="flex h-16 items-center justify-center">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
          </div>
        ) : !gateway ? (
          <div className="space-y-4">
            <p className="text-sm text-slate-400">No gateway configured.</p>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">IP Address</label>
              <input type="text" className={inputCls} value={ip}
                onChange={(e) => setIp(e.target.value)} placeholder="192.168.1.50" />
            </div>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={https} onChange={(e) => setHttps(e.target.checked)}
                className="h-4 w-4 rounded border-white/20 bg-white/5 accent-electric-blue" />
              <span className="text-sm text-slate-300">Use HTTPS</span>
            </label>
            <label className={`flex items-center gap-2.5 select-none ${https ? "cursor-pointer" : "cursor-not-allowed opacity-40"}`}>
              <input type="checkbox" checked={!verifySSL} onChange={(e) => setVerifySSL(!e.target.checked)}
                disabled={!https} className="h-4 w-4 rounded border-white/20 bg-white/5 accent-electric-blue" />
              <span className="text-sm text-slate-300">Ignore certificate errors</span>
            </label>
            {testResult && <TerminalResult result={testResult} />}
            {error && <p className="text-sm text-red-400">{error}</p>}
            <div className="flex gap-3">
              <button onClick={handleTest} disabled={testing || !ip}
                className="flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-slate-300 hover:text-white transition disabled:opacity-40">
                {testing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Test
              </button>
              <button onClick={handleSave} disabled={saving || !ip}
                className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-electric-blue py-2 text-sm font-semibold text-navy-900 hover:bg-electric-blue-light transition disabled:opacity-40">
                {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Save
              </button>
            </div>
          </div>
        ) : !editing ? (
          <div className="space-y-3">
            <div className="rounded-lg border border-white/10 bg-white/5 p-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">IP Address</span>
                <span className="font-mono text-white">{gateway.ip}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Protocol</span>
                <span className="font-mono text-white">{gateway.scheme}</span>
              </div>
              {gateway.scheme === "https" && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Verify SSL</span>
                  <span className={`font-mono ${gateway.verify_ssl ? "text-green-400" : "text-amber-400"}`}>
                    {gateway.verify_ssl ? "yes" : "no"}
                  </span>
                </div>
              )}
            </div>
            <button onClick={startEditing}
              className="w-full rounded-lg border border-white/15 bg-white/5 py-2 text-sm font-medium text-slate-300 hover:text-white hover:bg-white/10 transition">
              Edit
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">IP Address</label>
              <input type="text" className={inputCls} value={ip}
                onChange={(e) => setIp(e.target.value)} placeholder="192.168.1.50" />
            </div>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={https} onChange={(e) => setHttps(e.target.checked)}
                className="h-4 w-4 rounded border-white/20 bg-white/5 accent-electric-blue" />
              <span className="text-sm text-slate-300">Use HTTPS</span>
            </label>
            <label className={`flex items-center gap-2.5 select-none ${https ? "cursor-pointer" : "cursor-not-allowed opacity-40"}`}>
              <input type="checkbox" checked={!verifySSL} onChange={(e) => setVerifySSL(!e.target.checked)}
                disabled={!https} className="h-4 w-4 rounded border-white/20 bg-white/5 accent-electric-blue" />
              <span className="text-sm text-slate-300">Ignore certificate errors</span>
            </label>
            {testResult && <TerminalResult result={testResult} />}
            {error && <p className="text-sm text-red-400">{error}</p>}
            <div className="flex gap-3">
              <button onClick={handleTest} disabled={testing || !ip}
                className="flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-slate-300 hover:text-white transition disabled:opacity-40">
                {testing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Test
              </button>
              <button onClick={handleSave} disabled={saving || !ip}
                className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-electric-blue py-2 text-sm font-semibold text-navy-900 hover:bg-electric-blue-light transition disabled:opacity-40">
                {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Save
              </button>
              <button onClick={() => setEditing(false)}
                className="rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm text-slate-300 hover:text-white transition">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Danger zone */}
      {gateway && !isLoading && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-red-400">Danger Zone</h2>
          <p className="text-xs text-slate-400">
            Removes the gateway IP address from configuration.
          </p>
          <button onClick={handleReset}
            className="flex items-center gap-2 rounded-lg border border-red-500/40 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-500/10 transition">
            <Trash2 className="h-4 w-4" />
            Reset Gateway
          </button>
        </div>
      )}

      {/* Version */}
      <div className="flex justify-end">
        <span className="text-xs font-mono text-slate-600">{buildVersion()}</span>
      </div>
    </div>
  );
}
