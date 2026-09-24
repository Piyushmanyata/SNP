import { normalizePhone } from "./phone";

test.each([
  ["9876543210", "9876543210"],
  ["+91 98765 43210", "9876543210"],
  ["+91-98765-43210", "9876543210"],
  ["098765 43210", "9876543210"],
  ["919876543210", "9876543210"],
  ["98765432101", null],
  ["1234567890", null],
  ["0091 98765 43210", null],
  ["98765", null],
  ["", null],
  [null, null],
])("the household phone rule turns %p into %p, as the server does", (raw, canonical) => {
  expect(normalizePhone(raw)).toBe(canonical);
});
