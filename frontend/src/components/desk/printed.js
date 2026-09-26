import { displayTime } from "../../lib/dates";

function printedAt(p) {
  return `${displayTime(p.printed_at)}${p.printed_by_name ? ` by ${p.printed_by_name}` : ""}`;
}

export function printedLine(p) {
  return `Printed ${printedAt(p)}`;
}

export function alreadyPrintedLine(p) {
  return `Already printed at ${printedAt(p)}. To reprint, find them by name or reg #.`;
}
