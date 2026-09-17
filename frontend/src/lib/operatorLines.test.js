import { OPERATOR_LINES, LINE_STORAGE_KEY, effectiveLine, lineLabel, writeSessionLine } from "./operatorLines";

beforeEach(() => sessionStorage.clear());

test("operators choose their line without an account assignment or a separate Rx station", () => {
  expect(OPERATOR_LINES.map(({ key }) => key)).toEqual(["doctor_rx", "medicine", "specs_fixed", "specs_made", "ot"]);
  expect(effectiveLine({ role: "clinical_desk_operator", line: "medicine" })).toBeNull();
  writeSessionLine("specs_fixed");
  expect(effectiveLine({ role: "clinical_desk_operator", line: "medicine" })).toBe("specs_fixed");
});

test("the ot line carries its glossary name, Hospital", () => {
  expect(lineLabel("ot")).toBe("Hospital");
});

test("retired and invalid station preferences return to the picker", () => {
  sessionStorage.setItem(LINE_STORAGE_KEY, "rx");
  expect(effectiveLine({ role: "clinical_desk_operator" })).toBeNull();
  sessionStorage.setItem(LINE_STORAGE_KEY, "unknown");
  expect(effectiveLine({ role: "admin" })).toBeNull();
});
