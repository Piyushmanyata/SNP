export function displayDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  return match ? `${match[3]}-${match[2]}-${match[1]}` : value || "";
}

const IST_PARTS = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function displayTimestamp(value) {
  const instant = new Date(value || "");
  if (Number.isNaN(instant.getTime())) return value || "";
  const part = Object.fromEntries(IST_PARTS.formatToParts(instant).map((p) => [p.type, p.value]));
  return `${part.day}-${part.month}-${part.year} ${part.hour}:${part.minute}`;
}
