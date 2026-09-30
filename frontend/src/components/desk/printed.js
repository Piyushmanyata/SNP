import { displayTime } from "../../lib/dates";

export const PRINT_WINDOW_CLOSED_LINE = "The print window is closed.";
export const AWAITING_SCAN_LINE = "Scan their Aadhaar card, or record a No-card print";

function printedAt(p) {
  return `${displayTime(p.printed_at)}${p.printed_by_name ? ` by ${p.printed_by_name}` : ""}`;
}

export function printedLine(p) {
  return `Printed ${printedAt(p)}`;
}

export function alreadyPrintedLine(p) {
  return `Already printed at ${printedAt(p)}. To reprint, find them by name or reg #.`;
}
