import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { PrescriptionWizard, stepComplete, visibleSteps } from "./PrescriptionWizard";

global.IS_REACT_ACT_ENVIRONMENT = true;

const MEDICINES = [
  { id: "med-1", name: "Moxifloxacin", active: true },
  { id: "med-2", name: "Timolol", active: true },
];
const POWERS = [
  { id: "p1", value: -1.5, label: "-1.50", active: true },
  { id: "p2", value: 2, label: "+2.00", active: true },
];

const baseRx = {
  diagnosis_options: [],
  diagnosis_other: "",
  blood_sugar: "",
  bp: "",
  remarks: "",
  specs_measurements: { r_sph: "", r_cyl: "", r_axis: "", l_sph: "", l_cyl: "", l_axis: "", add: "" },
  ot_eye: "",
  ot_procedure: "",
  ot_notes: "",
  prescribed_medicine_ids: [],
  fixed_power_r: null,
  fixed_power_l: null,
  prescribed_lines: [],
  none_prescribed: false,
  full_transcription_confirmed: false,
};

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  container = null;
});

function renderWizard(rx, overrides = {}) {
  const setRx = jest.fn();
  act(() => {
    root.render(
      <PrescriptionWizard
        rx={rx}
        setRx={setRx}
        diagOpts={["Cataract"]}
        medicines={MEDICINES}
        powers={POWERS}
        toggleDiag={jest.fn()}
        locked={false}
        busy={false}
        saveStep={jest.fn()}
        completeRx={jest.fn()}
        setShowCorrection={jest.fn()}
        {...overrides}
      />,
    );
  });
  return setRx;
}

describe("wizard step pruning", () => {
  test("a patient with no lines walks only diagnosis, lines and review", () => {
    expect(visibleSteps(baseRx).map((s) => s.key)).toEqual(["diagnosis", "lines", "review"]);
  });

  test("a medicine-only patient never meets a specs or surgery step", () => {
    const rx = { ...baseRx, prescribed_lines: ["medicine"] };
    expect(visibleSteps(rx).map((s) => s.key)).toEqual([
      "diagnosis", "lines", "medicine", "review",
    ]);
  });

  test("every prescribed line adds exactly its own step, in a fixed order", () => {
    const rx = { ...baseRx, prescribed_lines: ["ot", "medicine", "specs_made"] };
    expect(visibleSteps(rx).map((s) => s.key)).toEqual([
      "diagnosis", "lines", "medicine", "specs_made", "ot", "review",
    ]);
  });
});

describe("step completion gates", () => {
  test("the lines step needs either lines or an explicit none, never both or neither", () => {
    expect(stepComplete("lines", baseRx)).toBe(false);
    expect(stepComplete("lines", { ...baseRx, prescribed_lines: ["medicine"] })).toBe(true);
    expect(stepComplete("lines", { ...baseRx, none_prescribed: true })).toBe(true);
    expect(stepComplete("lines", {
      ...baseRx, none_prescribed: true, prescribed_lines: ["medicine"],
    })).toBe(false);
  });

  test("medicine needs at least one pick", () => {
    expect(stepComplete("medicine", baseRx)).toBe(false);
    expect(stepComplete("medicine", { ...baseRx, prescribed_medicine_ids: ["med-1"] })).toBe(true);
  });

  test("fixed power needs both eyes and accepts a zero power", () => {
    expect(stepComplete("specs_fixed", baseRx)).toBe(false);
    expect(stepComplete("specs_fixed", { ...baseRx, fixed_power_r: 2 })).toBe(false);
    expect(stepComplete("specs_fixed", { ...baseRx, fixed_power_r: 0, fixed_power_l: 0 })).toBe(true);
  });

  test("made specs need both spheres and surgery needs eye and procedure", () => {
    expect(stepComplete("specs_made", {
      ...baseRx, specs_measurements: { r_sph: "-1.00", l_sph: "" },
    })).toBe(false);
    expect(stepComplete("specs_made", {
      ...baseRx, specs_measurements: { r_sph: "-1.00", l_sph: "-1.25" },
    })).toBe(true);
    expect(stepComplete("ot", { ...baseRx, ot_eye: "R" })).toBe(false);
    expect(stepComplete("ot", { ...baseRx, ot_eye: "R", ot_procedure: "Phaco" })).toBe(true);
  });

  test("review is gated on the paper attestation", () => {
    expect(stepComplete("review", baseRx)).toBe(false);
    expect(stepComplete("review", { ...baseRx, full_transcription_confirmed: true })).toBe(true);
  });
});

describe("wizard rendering", () => {
  test("Next is blocked on a step that has not been answered", () => {
    renderWizard(baseRx);
    act(() => container.querySelector('[data-testid="wizard-next"]').click());
    expect(container.querySelector('[data-testid="wizard-progress"]').textContent)
      .toContain("Step 2 of 3");
    expect(container.querySelector('[data-testid="wizard-next"]').disabled).toBe(true);
  });

  test("advancing calls saveStep so the draft survives an interruption", () => {
    const saveStep = jest.fn();
    renderWizard({ ...baseRx, diagnosis_options: ["Cataract"] }, { saveStep });
    act(() => container.querySelector('[data-testid="wizard-next"]').click());
    expect(saveStep).toHaveBeenCalled();
    expect(container.querySelector('[data-testid="prescribed-lines"]')).not.toBeNull();
  });

  test("vitals are hidden behind a control on review and never block completion", () => {
    renderWizard({ ...baseRx, none_prescribed: true, full_transcription_confirmed: true });
    act(() => container.querySelector('[data-testid="wizard-next"]').click());
    act(() => container.querySelector('[data-testid="wizard-next"]').click());
    expect(container.querySelector('[data-testid="bp-input"]')).toBeNull();
    expect(container.querySelector('[data-testid="complete-prescription-button"]').disabled).toBe(false);
    act(() => container.querySelector('[data-testid="add-vitals-button"]').click());
    expect(container.querySelector('[data-testid="bp-input"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="sugar-input"]')).not.toBeNull();
  });

  test("recorded vitals keep the panel open when the prescription is reopened", () => {
    renderWizard({ ...baseRx, none_prescribed: true, bp: "120/80" });
    act(() => container.querySelector('[data-testid="wizard-next"]').click());
    act(() => container.querySelector('[data-testid="wizard-next"]').click());
    expect(container.querySelector('[data-testid="bp-input"]').value).toBe("120/80");
  });

  test("the review step reads back the medicines and power that were picked", () => {
    renderWizard({
      ...baseRx,
      prescribed_lines: ["medicine", "specs_fixed"],
      prescribed_medicine_ids: ["med-2"],
      fixed_power_r: 2,
      fixed_power_l: -1.5,
      full_transcription_confirmed: true,
    });
    for (let i = 0; i < 4; i += 1) {
      const next = container.querySelector('[data-testid="wizard-next"]');
      if (next) act(() => next.click());
    }
    expect(container.querySelector('[data-testid="summary-medicines"]').textContent).toBe("Timolol");
    expect(container.querySelector('[data-testid="summary-fixed-power"]').textContent)
      .toBe("RE +2.00 · LE -1.50");
  });
});
