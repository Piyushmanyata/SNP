export const SMS_VENUE_MAX = 30;
const SMS_VENUE_MIN = 3;
const LINK = /https?:\/\/|www\.|\.(?:com|in|org|net|io|co|info|app|link|ly|me)\b/i;
const PHONE = /\p{Nd}(?:[\s-]?\p{Nd}){6,}/u;
const PLACEHOLDERS = new Set(["na", "n/a", "nil", "none", "null", "tbd", "tba", "test"]);

export const cleanSmsVenue = (raw) => (raw || "").split(/\s+/).filter(Boolean).join(" ");

export function smsVenueProblem(venue) {
  const length = [...venue].length;
  if (length < SMS_VENUE_MIN || length > SMS_VENUE_MAX) return `SMS venue must be ${SMS_VENUE_MIN} to ${SMS_VENUE_MAX} characters`;
  if (LINK.test(venue)) return "SMS venue must not contain a link";
  if (PHONE.test(venue)) return "SMS venue must not contain a phone number";
  if (PLACEHOLDERS.has(venue.replace(/^[ .-]+|[ .-]+$/g, "").toLowerCase())) return "SMS venue must name the place, not a placeholder";
  return null;
}

export function smsVenueFor(venue, venueSms) {
  const text = cleanSmsVenue(venueSms) || cleanSmsVenue(venue);
  return { text, length: [...text].length, problem: text ? smsVenueProblem(text) : null };
}

export const SMS_LABELS = {
  registration: "Registration confirmation",
  camp: "Camp reminder",
  ot_token: "OT Token SMS",
  ot: "OT reminder",
  specs_token: "Specs Token SMS",
  specs: "Specs reminder",
  ot_change: "OT date or venue change",
  specs_change: "Specs date or venue change",
};
