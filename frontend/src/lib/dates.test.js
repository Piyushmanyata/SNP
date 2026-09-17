import { displayDate, displayTimestamp } from "./dates";

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
