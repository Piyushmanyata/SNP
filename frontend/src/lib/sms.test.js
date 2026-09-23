import { cleanSmsVenue, smsVenueFor, smsVenueProblem } from "./sms";

test.each([
  ["Sikar Bhawan", null],
  ["Hansa Garden, Jasidih, Deoghar", null],
  ["बजाज हॉस्पिटल, देवघर", null],
  ["Deoghar 814142", null],
  ["Dr.Ambedkar Bhawan", null],
  ["NA", "SMS venue must be 3 to 30 characters"],
  ["Hansa Garden, Baghmara, Jasidih, Deoghar", "SMS venue must be 3 to 30 characters"],
  ["snpcamps.in hall", "SMS venue must not contain a link"],
  ["www.snp hall", "SMS venue must not contain a link"],
  ["Sikar Bhawan 98765 43210", "SMS venue must not contain a phone number"],
  ["Hall 9876-543210", "SMS venue must not contain a phone number"],
  ["हॉल ९८७६५४३२१०", "SMS venue must not contain a phone number"],
  ["N/A", "SMS venue must name the place, not a placeholder"],
  ["TBD.", "SMS venue must name the place, not a placeholder"],
  ["test", "SMS venue must name the place, not a placeholder"],
])("smsVenueProblem(%j) is %j", (venue, problem) => {
  expect(smsVenueProblem(venue)).toBe(problem);
});

test("the short name wins and spacing is tidied before counting", () => {
  expect(cleanSmsVenue("  Sikar   Bhawan ")).toBe("Sikar Bhawan");
  expect(smsVenueFor("A very long full address that no SMS variable can carry", "  Sikar  Bhawan "))
    .toEqual({ text: "Sikar Bhawan", length: 12, problem: null });
  expect(smsVenueFor("A very long full address that no SMS variable can carry", "").problem)
    .toBe("SMS venue must be 3 to 30 characters");
  expect(smsVenueFor("", "")).toEqual({ text: "", length: 0, problem: null });
});
