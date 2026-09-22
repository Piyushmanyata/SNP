import { displayDate, displayDateRange, displayTimestamp } from "./dates";

test("a date range reads as one date when it starts and ends on the same day", () => {
  expect(displayDateRange("2026-09-20", "2026-09-27")).toBe("20-09-2026 – 27-09-2026");
  expect(displayDateRange("2026-09-20", "2026-09-20")).toBe("20-09-2026");
  expect(displayDateRange("2026-09-20", null)).toBe("20-09-2026");
});

test("an ISO date is displayed as DD-MM-YYYY", () => {
  expect(displayDate("2026-09-17")).toBe("17-09-2026");
});

test("a missing date displays as nothing and anything else is left alone", () => {
  expect(displayDate(null)).toBe("");
  expect(displayDate("")).toBe("");
  expect(displayDate("tomorrow")).toBe("tomorrow");
});

test("a timestamp is displayed as DD-MM-YYYY HH:MM in IST", () => {
  expect(displayTimestamp("2026-09-16T20:15:00+00:00")).toBe("17-09-2026 01:45");
  expect(displayTimestamp(null)).toBe("");
});
