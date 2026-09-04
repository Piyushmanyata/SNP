export const ROSTER_STORAGE_KEY = "snp.roster";

export function readRoster() {
  try {
    const raw = sessionStorage.getItem(ROSTER_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !parsed.id || !parsed.name) return null;
    return { id: parsed.id, name: parsed.name };
  } catch {
    return null;
  }
}

export function writeRoster({ id, name }) {
  try {
    sessionStorage.setItem(ROSTER_STORAGE_KEY, JSON.stringify({ id, name }));
  } catch {
    /* ignore */
  }
}

export function clearRoster() {
  try {
    sessionStorage.removeItem(ROSTER_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function needsRoster(user) {
  return user?.role === "volunteer" || user?.role === "clinical_desk_operator";
}
