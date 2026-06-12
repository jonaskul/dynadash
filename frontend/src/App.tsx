import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { UISettingsProvider } from "./context/UISettings";
import Navbar from "./components/Navbar";
import AreaManagerView from "./views/AreaManagerView";
import ControlView from "./views/ControlView";
import EnergyView from "./views/EnergyView";
import HistoryView from "./views/HistoryView";
import SettingsView from "./views/SettingsView";
import SetupView from "./views/SetupView";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
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

export default function App() {
  return (
    <UISettingsProvider>
      <QueryClientProvider client={queryClient}>
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
      </QueryClientProvider>
    </UISettingsProvider>
  );
}
