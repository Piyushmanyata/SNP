export function normalizePhone(value) {
  const digits = String(value ?? "").replace(/\D/g, "");
  return digits.match(/^(?:91|0)?([6-9]\d{9})$/)?.[1] ?? null;
}
