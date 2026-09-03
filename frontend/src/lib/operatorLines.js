export const LINE_STORAGE_KEY = "snp.operatorLine";

export const OPERATOR_LINES = [
  { key: "rx", label: "Doctor's Rx" },
  { key: "medicine", label: "Medicine" },
  { key: "specs_fixed", label: "Fixed-power specs" },
  { key: "specs_made", label: "Spectacles to be made" },
  { key: "ot", label: "OT" },
];

export function lineLabel(key) {
  return OPERATOR_LINES.find((l) => l.key === key)?.label || key;
}

export function readSessionLine() {
  try {
    return sessionStorage.getItem(LINE_STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

export function writeSessionLine(key) {
  try {
    if (key) sessionStorage.setItem(LINE_STORAGE_KEY, key);
    else sessionStorage.removeItem(LINE_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function clearSessionLine() {
  writeSessionLine(null);
}

export function effectiveLine(user) {
  if (!user) return null;
  const session = readSessionLine();
  if (session) return session;
  if (user.role === "admin") return null;
  return user.line || null;
}
