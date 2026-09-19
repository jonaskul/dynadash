import { useState } from "react";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { login, setupPassword } from "../api/client";

const MIN_LENGTH = 10;

const inputCls =
  "w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none transition focus:border-electric-blue/60 focus:ring-1 focus:ring-electric-blue/30 dark:border-white/15 dark:bg-white/5 dark:text-white dark:placeholder-slate-500";

/**
 * Sign-in gate. Doubles as the first-run screen: when the backend reports that
 * no password exists yet, this creates one instead of checking one.
 */
export default function LoginView({
  needsSetup,
  onAuthenticated,
}: {
  needsSetup: boolean;
  onAuthenticated: () => void;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tooShort = needsSetup && password.length > 0 && password.length < MIN_LENGTH;
  const mismatch = needsSetup && confirm.length > 0 && password !== confirm;
  const canSubmit =
    password.length > 0 &&
    !busy &&
    (!needsSetup || (password.length >= MIN_LENGTH && password === confirm));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      if (needsSetup) {
        await setupPassword(password);
      } else {
        await login(password);
      }
      onAuthenticated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setPassword("");
      setConfirm("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4 dark:bg-navy-950">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-5 rounded-xl border border-slate-200 bg-white p-6 dark:border-white/10 dark:bg-navy-800/60"
      >
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-electric-blue/15 text-electric-blue">
            {needsSetup ? (
              <ShieldCheck className="h-5 w-5" />
            ) : (
              <KeyRound className="h-5 w-5" />
            )}
          </span>
          <div>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-white">
              {needsSetup ? "Choose a password" : "DynaDash"}
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {needsSetup
                ? "This protects the dashboard for everyone in the house."
                : "Enter the dashboard password to continue."}
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <label
              htmlFor="password"
              className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoFocus
              autoComplete={needsSetup ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••"
              className={inputCls}
            />
            {needsSetup && (
              <p
                className={`mt-1 text-xs ${
                  tooShort
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-slate-400 dark:text-slate-500"
                }`}
              >
                At least {MIN_LENGTH} characters.
              </p>
            )}
          </div>

          {needsSetup && (
            <div>
              <label
                htmlFor="confirm"
                className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400"
              >
                Repeat password
              </label>
              <input
                id="confirm"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="••••••••••"
                className={inputCls}
              />
              {mismatch && (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                  The two passwords do not match.
                </p>
              )}
            </div>
          )}
        </div>

        {error && <p className="text-sm text-red-500 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={!canSubmit}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-electric-blue py-2.5 text-sm font-semibold text-navy-900 transition hover:bg-electric-blue-light disabled:opacity-40"
        >
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          {needsSetup ? "Create password" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
