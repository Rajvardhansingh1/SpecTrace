"use client";

import { useEffect, useState } from "react";

export type Theme = "system" | "light" | "dark";
export const THEME_KEY = "spectrace-theme";

const OPTIONS: { value: Theme; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

/** Storage can throw (private windows, blocked site data), so every access is guarded. */
export function readStoredTheme(): Theme {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

export function ThemeToggle() {
  // Server and first client render agree on "system"; the stored choice is applied after mount.
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    // The inline script in the layout already set the attribute; this only syncs the buttons.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(readStoredTheme());
  }, []);

  function choose(next: Theme) {
    setTheme(next);
    applyTheme(next);
    try {
      if (next === "system") window.localStorage.removeItem(THEME_KEY);
      else window.localStorage.setItem(THEME_KEY, next);
    } catch {
      /* The choice still applies for this visit. */
    }
  }

  return (
    <div className="theme" role="group" aria-label="Color theme">
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          className="theme__option"
          aria-pressed={theme === option.value}
          onClick={() => choose(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
