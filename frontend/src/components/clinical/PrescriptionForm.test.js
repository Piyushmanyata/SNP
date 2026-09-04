import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { PrescriptionForm } from "./PrescriptionForm";

global.IS_REACT_ACT_ENVIRONMENT = true;

const emptyRx = {
  diagnosis_options: [],
  diagnosis_other: "",
  blood_sugar: "",
  bp: "",
  remarks: "",
  specs_measurements: {
    r_sph: "", r_cyl: "", r_axis: "", l_sph: "", l_cyl: "", l_axis: "", add: "",
  },
  ot_eye: "",
  ot_procedure: "",
};

const ORDER = [
  "diagnosis-options",
  "diagnosis-other-input",
  "sugar-input",
  "bp-input",
  "remarks-input",
  "ot-eye-select",
  "ot-procedure-input",
  "specs-r_sph",
  "specs-r_cyl",
  "specs-r_axis",
  "specs-l_sph",
  "specs-l_cyl",
  "specs-l_axis",
  "specs-add",
];

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
});

afterEach(() => {
  act(() => { root.unmount(); });
  container.remove();
});

describe("PrescriptionForm", () => {
  test("DOM order matches Doctor's Rx paper", async () => {
    await act(async () => {
      root.render(
        <PrescriptionForm
          rx={emptyRx}
          setRx={() => {}}
          diagOpts={["Cataract"]}
          toggleDiag={() => {}}
          locked={false}
          busy={false}
          saveRx={() => {}}
        />,
      );
    });
    const form = container.querySelector('[data-testid="clinical-prescription-form"]');
    const ids = [...form.querySelectorAll("[data-testid]")]
      .map((el) => el.getAttribute("data-testid"))
      .filter((id) => ORDER.includes(id));
    expect(ids).toEqual(ORDER);
  });

  test("Enter in the BP field calls saveRx", async () => {
    const saveRx = jest.fn();
    await act(async () => {
      root.render(
        <PrescriptionForm
          rx={emptyRx}
          setRx={() => {}}
          diagOpts={[]}
          toggleDiag={() => {}}
          locked={false}
          busy={false}
          saveRx={saveRx}
        />,
      );
    });
    const bp = container.querySelector('[data-testid="bp-input"]');
    await act(async () => {
      bp.focus();
      bp.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
      bp.closest("form").requestSubmit();
    });
    expect(saveRx).toHaveBeenCalled();
  });
});
