import { createContext, useContext, useEffect, useState } from "react";

interface UISettingsValue {
  use24h: boolean;
  lightMode: boolean;
  setUse24h: (v: boolean) => void;
  setLightMode: (v: boolean) => void;
}

const STORAGE_KEY = "dynadash-ui";

function loadSettings(): { use24h: boolean; lightMode: boolean } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return { use24h: true, lightMode: false };
}

const UISettingsContext = createContext<UISettingsValue>({
  use24h: true,
  lightMode: false,
  setUse24h: () => {},
  setLightMode: () => {},
});

export function UISettingsProvider({ children }: { children: React.ReactNode }) {
  const initial = loadSettings();
  const [use24h, setUse24hState] = useState(initial.use24h);
  const [lightMode, setLightModeState] = useState(initial.lightMode);

  function persist(next: { use24h: boolean; lightMode: boolean }) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }

  function setUse24h(v: boolean) {
    setUse24hState(v);
    persist({ use24h: v, lightMode });
  }

  function setLightMode(v: boolean) {
    setLightModeState(v);
    persist({ use24h, lightMode: v });
  }

  useEffect(() => {
    document.documentElement.classList.toggle("dark", !lightMode);
  }, [lightMode]);

  // Apply on first render
  useEffect(() => {
    document.documentElement.classList.toggle("dark", !initial.lightMode);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <UISettingsContext.Provider value={{ use24h, lightMode, setUse24h, setLightMode }}>
      {children}
    </UISettingsContext.Provider>
  );
}

export function useUISettings() {
  return useContext(UISettingsContext);
}

export function useClockFormat() {
  const { use24h } = useUISettings();
  return function formatTime(date: Date, showSeconds = true): string {
    return date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      ...(showSeconds ? { second: "2-digit" } : {}),
      hour12: !use24h,
    });
  };
}
