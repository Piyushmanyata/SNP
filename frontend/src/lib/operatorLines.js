export const LINE_STORAGE_KEY = "snp.operatorLine";

export const OPERATOR_LINES = [
  { key: "doctor_rx", label: "Doctor Rx" },
  { key: "medicine", label: "Medicine" },
  { key: "specs_fixed", label: "Fixed-power specs" },
  { key: "specs_made", label: "Spectacles to be made" },
  { key: "ot", label: "Hospital" },
];

export function lineLabel(key) {
  return OPERATOR_LINES.find((l) => l.key === key)?.label || key;
}

export function readSessionLine() {
  try {
    const line = sessionStorage.getItem(LINE_STORAGE_KEY);
    return OPERATOR_LINES.some(({ key }) => key === line) ? line : null;
  } catch {
    return null;
  }
}

export function writeSessionLine(key) {
  try {
    if (key) sessionStorage.setItem(LINE_STORAGE_KEY, key);
    else sessionStorage.removeItem(LINE_STORAGE_KEY);
  } catch {}
}

export function clearSessionLine() {
  writeSessionLine(null);
}

export function effectiveLine(user) {
  return user ? readSessionLine() : null;
}
