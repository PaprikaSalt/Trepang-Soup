import type { PersistedSession } from "../protocol/types";

const SESSION_KEY = "trepang-soup.session";
const CLIENT_INSTANCE_KEY = "trepang-soup.client-instance";

export function loadSession(): PersistedSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as PersistedSession) : null;
  } catch {
    return null;
  }
}

export function saveSession(session: PersistedSession): void {
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  window.localStorage.removeItem(SESSION_KEY);
}

export function getClientInstanceId(): string {
  const existing = window.localStorage.getItem(CLIENT_INSTANCE_KEY);
  if (existing) return existing;

  const value = `client_${crypto.randomUUID().replace(/-/g, "")}`;
  window.localStorage.setItem(CLIENT_INSTANCE_KEY, value);
  return value;
}
