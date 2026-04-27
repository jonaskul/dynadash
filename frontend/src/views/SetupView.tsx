import { Loader2, Zap } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { saveGateway, testGateway } from "../api/client";

const inputCls = "w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2.5 text-sm text-white placeholder-slate-500 outline-none transition focus:border-electric-blue/60 focus:ring-1 focus:ring-electric-blue/30";

function Checkbox({ checked, onChange, disabled, label }: {
  checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label: string;
}) {
  return (
    <label className={`flex items-center gap-2.5 select-none ${disabled ? "cursor-not-allowed opacity-40" : "cursor-pointer"}`}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        disabled={disabled} className="h-4 w-4 rounded border-white/20 bg-white/5 accent-electric-blue" />
      <span className="text-sm text-slate-300">{label}</span>
    </label>
  );
}

export default function SetupView() {
  const navigate = useNavigate();

  const [ip, setIp] = useState("");
  const [https, setHttps] = useState(false);
  const [verifySSL, setVerifySSL] = useState(true);
  const [useAuth, setUseAuth] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; url: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scheme = https ? "https" : "http";

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
            <label className="mb-1 block text-sm font-medium text-slate-300">Gateway IP Address</label>
            <input type="text" value={ip} onChange={(e) => setIp(e.target.value)}
              placeholder="192.168.1.50" className={inputCls} />
          </div>

          <Checkbox checked={https} onChange={setHttps} label="Use HTTPS" />
          <Checkbox checked={!verifySSL} onChange={(v) => setVerifySSL(!v)}
            disabled={!https} label="Ignore certificate errors" />
          <Checkbox checked={useAuth} onChange={setUseAuth} label="Require authentication" />

          {useAuth && (
            <div className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-400">Username</label>
                <input type="text" value={username} onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin" className={inputCls} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-400">Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••" className={inputCls} />
              </div>
            </div>
          )}
        </div>

        {/* Test connection result */}
        {testResult && (
          <div className="mt-4 rounded-lg bg-black/60 border border-white/10 p-3 font-mono text-xs space-y-1">
            <div className="text-slate-400 break-all">
              <span className="text-green-400">$</span> GET {testResult.url}
            </div>
            <div className={testResult.success ? "text-green-400" : "text-red-400"}>
              <span className="text-slate-500">&gt;</span> {testResult.message}
            </div>
          </div>
        )}

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        <div className="mt-6 flex flex-col gap-3">
          <button onClick={handleTest} disabled={testing || !ip}
            className="flex items-center justify-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed">
            {testing && <Loader2 className="h-4 w-4 animate-spin" />}
            Test Connection
          </button>
          <button onClick={handleSave} disabled={saving || !ip}
            className="flex items-center justify-center gap-2 rounded-lg bg-electric-blue px-4 py-2.5 text-sm font-semibold text-navy-900 transition hover:bg-electric-blue-light disabled:opacity-40 disabled:cursor-not-allowed">
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Save &amp; Continue
          </button>
        </div>
      </div>
    </div>
  );
}
