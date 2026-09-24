import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { ReadOnlyPrescription } from "./ReadOnlyPrescription";
import { HistoryModal } from "./HistoryModal";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const q = (id) => container.querySelector(`[data-testid="${id}"]`);

test("a saved IOL surgery shows its eye and notes and no procedure", () => {
  act(() => root.render(<ReadOnlyPrescription transcription={{
    id: "tx-1", ot_outcome: "iol_surgery", ot_eye: "L", ot_notes: "Right eye also prescribed",
  }} />));
  expect(q("readonly-hospital").textContent).toBe("Hospital:IOL surgery · Left eye");
  expect(q("readonly-hospital-notes").textContent).toBe("Hospital notes:Right eye also prescribed");
  expect(container.textContent).not.toContain("procedure");
});

test("a saved referral reads Hospital referral", () => {
  act(() => root.render(<ReadOnlyPrescription transcription={{ id: "tx-2", ot_outcome: "referral" }} />));
  expect(q("readonly-hospital").textContent).toBe("Hospital:Hospital referral");
});

test("clinical history shows each visit date as DD-MM-YYYY", () => {
  act(() => root.render(<HistoryModal open onClose={jest.fn()} history={[
    { reg_no: 7, camp_name: "Spring camp", transcription: { id: "tx-9", created_at: "2026-03-03T20:15:00Z" } },
  ]} />));
  expect(document.body.textContent).toContain("04-03-2026");
  expect(document.body.textContent).not.toContain("2026-03-0");
});

test("the saved prescription lists what was prescribed and shows only those lines", () => {
  act(() => root.render(<ReadOnlyPrescription lines={["medicine"]} transcription={{
    id: "tx-3", prescribed_medicines: [{ name: "Moxifloxacin" }], fixed_power_r: 2, fixed_power_l: 2,
    specs_measurements: { r_sph: "-1.00", l_sph: "-1.00" },
  }} />));
  expect(q("readonly-prescribed").textContent).toBe("Prescribed:Medicine");
  expect(container.textContent).toContain("Moxifloxacin");
  expect(q("readonly-fixed-power")).toBeNull();
  expect(q("readonly-powers")).toBeNull();
  expect(q("readonly-hospital")).toBeNull();
});
