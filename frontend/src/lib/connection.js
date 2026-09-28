let offline = typeof navigator !== "undefined" && navigator.onLine === false;
const listeners = new Set();

export function setOffline(next) {
  if (offline === next) return;
  offline = next;
  listeners.forEach((listener) => listener());
}

export function isOffline() {
  return offline;
}

export function subscribeConnection(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

window.addEventListener("offline", () => setOffline(true));
