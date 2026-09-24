import { withLines } from "./prescriptionRules";

const FULL = {
  prescribed_lines: ["medicine", "specs_fixed", "specs_made", "ot"],
  prescribed_medicine_ids: ["med-1"],
  fixed_power_r: 2, fixed_power_l: 2,
  specs_measurements: { r_sph: "-1.00", l_sph: "-1.25" },
  ot_outcome: "referral", ot_eye: null,
};

test("unticking a line clears what it carried", () => {
  const rx = withLines(FULL, []);
  expect(rx.prescribed_lines).toEqual([]);
  expect(rx.prescribed_medicine_ids).toEqual([]);
  expect(rx.fixed_power_r).toBeNull();
  expect(rx.fixed_power_l).toBeNull();
  expect(rx.specs_measurements).toEqual({});
  expect(rx.ot_outcome).toBeNull();
});

test("a line that stays ticked keeps its content", () => {
  const rx = withLines(FULL, ["medicine", "specs_made"]);
  expect(rx.prescribed_medicine_ids).toEqual(["med-1"]);
  expect(rx.specs_measurements).toEqual(FULL.specs_measurements);
  expect(rx.fixed_power_r).toBeNull();
});
