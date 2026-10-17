const KEY = "spectrace-owner";
const VALID = /^[A-Za-z0-9_-]{16,128}$/;

let memory: string | null = null;

/**
 * A random value that identifies this browser to the API, so a visitor sees only their own
 * comparisons. There are no accounts: clearing site data starts a new, empty history. Only a hash
 * of the value is stored on the server.
 */
export function ownerToken(): string {
  if (typeof window === "undefined") return "";
  if (memory) return memory;
  try {
    const stored = window.localStorage.getItem(KEY);
    if (stored && VALID.test(stored)) return (memory = stored);
  } catch {
    /* Blocked storage: the token then lives for this page visit only. */
  }
  const bytes = new Uint8Array(24);
  window.crypto.getRandomValues(bytes);
  const token = btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  memory = token;
  try {
    window.localStorage.setItem(KEY, token);
  } catch {
    /* See above. */
  }
  return token;
}

/** For tests. */
export function resetOwnerTokenCache() {
  memory = null;
}
