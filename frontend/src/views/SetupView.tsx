import { CheckCircle, Loader2, XCircle, Zap } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { saveGateway, testGateway } from "../api/client";

export default function SetupView() {
  const navigate = useNavigate();

  const [ip, setIp] = useState("");
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleTest() {
    if (!ip) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testGateway({ ip });
      setTestResult(result);
    } catch (e) {
      setTestResult({ success: false, message: String(e) });
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    if (!ip) {
      setError("IP address is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveGateway({ ip });
      navigate("/areas");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy-950 px-4">
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-navy-800/80 p-8 backdrop-blur-sm shadow-2xl animate-fade-in">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-electric-blue/10 border border-electric-blue/30">
            <Zap className="h-7 w-7 text-electric-blue" fill="currentColor" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold tracking-widest text-white">
              DYNA<span className="text-electric-blue">DASH</span>
            </h1>
            <p className="mt-1 text-sm text-slate-400">Enter your Dynalite gateway IP address</p>
          </div>
        </div>

        {/* Fields */}
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">
              Gateway IP Address
            </label>
            <input
              type="text"
              value={ip}
              onChange={(e) => setIp(e.target.value)}
              placeholder="192.168.1.50"
              className="w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2.5 text-sm text-white placeholder-slate-500 outline-none transition focus:border-electric-blue/60 focus:ring-1 focus:ring-electric-blue/30"
            />
          </div>
        </div>

        {/* Test connection result */}
        {testResult && (
          <div
            className={`mt-4 flex items-center gap-2 rounded-lg p-3 text-sm ${
              testResult.success
                ? "bg-green-500/10 border border-green-500/30 text-green-400"
                : "bg-red-500/10 border border-red-500/30 text-red-400"
            }`}
          >
            {testResult.success ? (
              <CheckCircle className="h-4 w-4 shrink-0" />
            ) : (
              <XCircle className="h-4 w-4 shrink-0" />
            )}
            {testResult.message}
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="mt-3 text-sm text-red-400">{error}</p>
        )}

        {/* Actions */}
        <div className="mt-6 flex flex-col gap-3">
          <button
            onClick={handleTest}
            disabled={testing || !ip}
            className="flex items-center justify-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {testing && <Loader2 className="h-4 w-4 animate-spin" />}
            Test Connection
          </button>

          <button
            onClick={handleSave}
            disabled={saving || !ip}
            className="flex items-center justify-center gap-2 rounded-lg bg-electric-blue px-4 py-2.5 text-sm font-semibold text-navy-900 transition hover:bg-electric-blue-light disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Save &amp; Continue
          </button>
        </div>
      </div>
    </div>
  );
}
