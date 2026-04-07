import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, Loader2, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { deleteGateway, getGateway, saveGateway, testGateway } from "../api/client";

export default function SettingsView() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: gateway, isLoading } = useQuery({
    queryKey: ["gateway"],
    queryFn: getGateway,
    staleTime: 30_000,
  });

  const [ip, setIp] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [editing, setEditing] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function startEditing() {
    setIp(gateway?.ip ?? "");
    setUsername(gateway?.username ?? "");
    setPassword("");
    setTestResult(null);
    setError(null);
    setEditing(true);
  }

  async function handleTest() {
    if (!ip || !username) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testGateway({ ip, username, password });
      setTestResult(result);
    } catch (e) {
      setTestResult({ success: false, message: String(e) });
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    if (!ip || !username) { setError("IP and username are required."); return; }
    setSaving(true);
    setError(null);
    try {
      await saveGateway({ ip, username, password });
      queryClient.invalidateQueries({ queryKey: ["gateway"] });
      setEditing(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    if (!confirm("Remove gateway configuration? You will need to reconfigure on the setup screen.")) return;
    try {
      await deleteGateway();
      queryClient.invalidateQueries({ queryKey: ["gateway"] });
      navigate("/setup");
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
          <div>
            <p className="text-sm text-slate-400 mb-3">No gateway configured.</p>
            <button onClick={() => navigate("/setup")}
              className="rounded-lg bg-electric-blue px-4 py-2 text-sm font-semibold text-navy-900 hover:bg-electric-blue-light transition">
              Configure Gateway
            </button>
          </div>
        ) : !editing ? (
          <div className="space-y-3">
            <div className="rounded-lg border border-white/10 bg-white/5 p-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">IP Address</span>
                <span className="font-mono text-white">{gateway.ip}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Username</span>
                <span className="font-mono text-white">{gateway.username}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Password</span>
                <span className="font-mono text-slate-500">***</span>
              </div>
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
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Username</label>
              <input type="text" className={inputCls} value={username}
                onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">
                Password <span className="text-slate-500">(leave blank to keep current)</span>
              </label>
              <input type="password" className={inputCls} value={password}
                onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
            </div>

            {testResult && (
              <div className={`flex items-center gap-2 rounded-lg p-3 text-sm ${
                testResult.success
                  ? "bg-green-500/10 border border-green-500/30 text-green-400"
                  : "bg-red-500/10 border border-red-500/30 text-red-400"
              }`}>
                {testResult.success ? <CheckCircle className="h-4 w-4 shrink-0" /> : <XCircle className="h-4 w-4 shrink-0" />}
                {testResult.message}
              </div>
            )}

            {error && <p className="text-sm text-red-400">{error}</p>}

            <div className="flex gap-3">
              <button onClick={handleTest} disabled={testing || !ip || !username}
                className="flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-slate-300 hover:text-white transition disabled:opacity-40">
                {testing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Test
              </button>
              <button onClick={handleSave} disabled={saving || !ip || !username}
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
            Resetting the gateway will clear all connection settings and return you to the setup screen.
          </p>
          <button onClick={handleReset}
            className="flex items-center gap-2 rounded-lg border border-red-500/40 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-500/10 transition">
            <Trash2 className="h-4 w-4" />
            Reset Gateway
          </button>
        </div>
      )}
    </div>
  );
}
