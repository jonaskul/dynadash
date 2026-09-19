import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { UnauthorizedError, getAuthStatus, onUnauthorized } from "./api/client";
import { UISettingsProvider } from "./context/UISettings";
import Navbar from "./components/Navbar";
import AreaManagerView from "./views/AreaManagerView";
import ControlView from "./views/ControlView";
import EnergyView from "./views/EnergyView";
import HistoryView from "./views/HistoryView";
import LoginView from "./views/LoginView";
import SettingsView from "./views/SettingsView";
import SetupView from "./views/SetupView";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retrying a 401 only delays the login screen.
      retry: (count, error) => !(error instanceof UnauthorizedError) && count < 1,
      staleTime: 10_000,
    },
  },
});

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 dark:bg-navy-950 dark:text-white">
      <Navbar />
      <main>{children}</main>
    </div>
  );
}

type Gate =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "setup" }
  | { state: "login" }
  | { state: "ready" };

/**
 * Decides between the dashboard and the login screen, and swaps back to login
 * the moment any request reports that the session is gone.
 */
function AuthGate({ children }: { children: React.ReactNode }) {
  const [gate, setGate] = useState<Gate>({ state: "loading" });

  const check = useCallback(async () => {
    try {
      const status = await getAuthStatus();
      if (!status.configured) setGate({ state: "setup" });
      else if (!status.authenticated) setGate({ state: "login" });
      else setGate({ state: "ready" });
    } catch (err) {
      setGate({
        state: "error",
        message: err instanceof Error ? err.message : "Backend unreachable",
      });
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  useEffect(
    () =>
      onUnauthorized(() => {
        // Drop cached answers from the previous session before showing login,
        // so the next sign-in does not start from another account's data.
        setGate((current) =>
          current.state === "ready" ? { state: "login" } : current
        );
        queryClient.clear();
      }),
    []
  );

  if (gate.state === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 dark:bg-navy-950">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
      </div>
    );
  }

  if (gate.state === "error") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4 dark:bg-navy-950">
        <div className="max-w-sm space-y-3 rounded-xl border border-slate-200 bg-white p-6 text-center dark:border-white/10 dark:bg-navy-800/60">
          <p className="text-sm font-medium text-slate-900 dark:text-white">
            Cannot reach the backend
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400">{gate.message}</p>
          <button
            onClick={check}
            className="rounded-lg bg-electric-blue px-4 py-2 text-sm font-semibold text-navy-900 transition hover:bg-electric-blue-light"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (gate.state !== "ready") {
    return (
      <LoginView
        needsSetup={gate.state === "setup"}
        onAuthenticated={() => {
          queryClient.clear();
          setGate({ state: "ready" });
        }}
      />
    );
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <UISettingsProvider>
      <QueryClientProvider client={queryClient}>
        <AuthGate>
        <BrowserRouter>
          <Routes>
            <Route
              path="/setup"
              element={<SetupView />}
            />
            <Route
              path="/"
              element={
                <Layout>
                  <ControlView />
                </Layout>
              }
            />
            <Route
              path="/history"
              element={
                <Layout>
                  <HistoryView />
                </Layout>
              }
            />
            <Route
              path="/energy"
              element={
                <Layout>
                  <EnergyView />
                </Layout>
              }
            />
            <Route
              path="/areas"
              element={
                <Layout>
                  <AreaManagerView />
                </Layout>
              }
            />
            <Route
              path="/settings"
              element={
                <Layout>
                  <SettingsView />
                </Layout>
              }
            />
          </Routes>
        </BrowserRouter>
        </AuthGate>
      </QueryClientProvider>
    </UISettingsProvider>
  );
}
