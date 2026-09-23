import React, { act, useState } from "react";
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
  ot_outcome: null,
  ot_eye: null,
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
let latestRx = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  latestRx = null;
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  container = null;
});

function wizardProps(overrides) {
  return {
    diagOpts: ["Cataract"],
    medicines: MEDICINES,
    powers: POWERS,
    toggleDiag: jest.fn(),
    busy: false,
    saveStep: jest.fn(),
    completeRx: jest.fn(),
    ...overrides,
  };
}

function renderWizard(rx, overrides = {}) {
  const setRx = jest.fn();
  act(() => {
    root.render(<PrescriptionWizard rx={rx} setRx={setRx} {...wizardProps(overrides)} />);
  });
  return setRx;
}

function Live({ initial }) {
  const [rx, setRx] = useState(initial);
  latestRx = rx;
  return <PrescriptionWizard rx={rx} setRx={setRx} {...wizardProps()} />;
}

function renderLive(rx) {
  act(() => root.render(<Live initial={rx} />));
}

const q = (id) => container.querySelector(`[data-testid="${id}"]`);

async function next(times = 1) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => q("wizard-next").click());
  }
}

describe("wizard save errors", () => {
  test("a save error shows beside the step buttons", () => {
    renderWizard(baseRx, { error: "Draft save failed" });
    const alert = q("clinical-prescription-form").querySelector('[role="alert"]');
    expect(alert.textContent).toContain("Draft save failed");
    expect(alert.nextElementSibling.contains(q("wizard-next"))).toBe(true);
  });
});

describe("wizard step pruning", () => {
  test("a patient with no lines walks only diagnosis, lines and review", () => {
    expect(visibleSteps(baseRx).map((s) => s.key)).toEqual(["diagnosis", "lines", "review"]);
  });

  test("a medicine-only patient never meets a specs or Hospital step", () => {
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

  test("the lines step refuses two specs lines or IOL surgery beside a specs line", () => {
    expect(stepComplete("lines", { ...baseRx, prescribed_lines: ["specs_fixed", "specs_made"] })).toBe(false);
    expect(stepComplete("lines", {
      ...baseRx, prescribed_lines: ["specs_fixed", "ot"], ot_outcome: "iol_surgery", ot_eye: "R",
    })).toBe(false);
    expect(stepComplete("lines", {
      ...baseRx, prescribed_lines: ["specs_made", "ot"], ot_outcome: "referral",
    })).toBe(true);
    expect(stepComplete("lines", {
      ...baseRx, prescribed_lines: ["medicine", "ot"], ot_outcome: "iol_surgery", ot_eye: "L",
    })).toBe(true);
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

  test("made specs need both spheres", () => {
    expect(stepComplete("specs_made", {
      ...baseRx, specs_measurements: { r_sph: "-1.00", l_sph: "" },
    })).toBe(false);
    expect(stepComplete("specs_made", {
      ...baseRx, specs_measurements: { r_sph: "-1.00", l_sph: "-1.25" },
    })).toBe(true);
  });

  test("the Hospital step needs an outcome, and IOL surgery needs one eye and no specs line", () => {
    const ot = { ...baseRx, prescribed_lines: ["ot"] };
    expect(stepComplete("ot", ot)).toBe(false);
    expect(stepComplete("ot", { ...ot, ot_outcome: "referral" })).toBe(true);
    expect(stepComplete("ot", { ...ot, ot_outcome: "iol_surgery" })).toBe(false);
    expect(stepComplete("ot", { ...ot, ot_outcome: "iol_surgery", ot_eye: "B" })).toBe(false);
    expect(stepComplete("ot", { ...ot, ot_outcome: "iol_surgery", ot_eye: "R" })).toBe(true);
    expect(stepComplete("ot", {
      ...ot, prescribed_lines: ["ot", "specs_fixed"], ot_outcome: "iol_surgery", ot_eye: "R",
    })).toBe(false);
  });

  test("review is gated on the paper attestation", () => {
    expect(stepComplete("review", baseRx)).toBe(false);
    expect(stepComplete("review", { ...baseRx, full_transcription_confirmed: true })).toBe(true);
  });
});

describe("wizard rendering", () => {
  test("Next is blocked on a step that has not been answered", async () => {
    renderWizard(baseRx);
    await next();
    expect(q("wizard-progress").textContent).toContain("Step 2 of 3");
    expect(q("wizard-next").disabled).toBe(true);
  });

  test("advancing calls saveStep so the draft survives an interruption", async () => {
    const saveStep = jest.fn();
    renderWizard({ ...baseRx, diagnosis_options: ["Cataract"] }, { saveStep });
    await next();
    expect(saveStep).toHaveBeenCalled();
    expect(q("prescribed-lines")).not.toBeNull();
  });

  test("the lines step stops a second specs line and names the clash", async () => {
    renderLive({ ...baseRx, prescribed_lines: ["specs_fixed"] });
    await next();
    expect(q("prescribed-lines").textContent).toContain("Hospital");
    expect(q("prescribed-specs_made").disabled).toBe(true);
    expect(q("prescribed-specs_made-blocked").textContent)
      .toBe("Fixed-power specs and Spectacles to be made cannot be on one prescription.");
    expect(q("prescribed-ot").disabled).toBe(false);
    expect(q("prescribed-medicine").disabled).toBe(false);
    act(() => q("prescribed-ot").click());
    act(() => q("prescribed-medicine").click());
    expect(latestRx.prescribed_lines).toEqual(["specs_fixed", "ot", "medicine"]);
  });

  test("specs lines are stopped once IOL surgery is chosen", async () => {
    renderLive({ ...baseRx, prescribed_lines: ["ot"], ot_outcome: "iol_surgery", ot_eye: "R" });
    await next();
    expect(q("prescribed-specs_fixed").disabled).toBe(true);
    expect(q("prescribed-specs_fixed-blocked").textContent)
      .toBe("Fixed-power specs and IOL surgery cannot be on one prescription.");
    expect(q("prescribed-medicine").disabled).toBe(false);
  });

  test("unticking Hospital clears the outcome and eye", async () => {
    renderLive({ ...baseRx, prescribed_lines: ["ot"], ot_outcome: "iol_surgery", ot_eye: "R" });
    await next();
    act(() => q("prescribed-ot").click());
    expect(latestRx).toEqual(expect.objectContaining({
      prescribed_lines: [], ot_outcome: null, ot_eye: null,
    }));
  });

  test("the Hospital step asks IOL surgery or referral, one eye for surgery, and optional vitals", async () => {
    renderLive({ ...baseRx, prescribed_lines: ["ot"] });
    await next(2);
    expect(q("wizard-progress").textContent).toContain("Step 3 of 4");
    expect(container.querySelector("h3").textContent).toBe("Hospital");
    expect(q("ot-procedure-input")).toBeNull();
    expect(q("ot-eye-select")).toBeNull();
    expect(q("ot-notes-input")).not.toBeNull();
    expect(q("bp-input")).not.toBeNull();
    expect(q("sugar-input")).not.toBeNull();
    expect(q("wizard-next").disabled).toBe(true);

    act(() => q("ot-outcome-iol_surgery").click());
    expect(latestRx.ot_outcome).toBe("iol_surgery");
    const eye = q("ot-eye-select");
    expect([...eye.options].map((o) => o.textContent)).toEqual(["—", "Right", "Left"]);
    expect(q("wizard-next").disabled).toBe(true);
    act(() => {
      eye.value = "L";
      eye.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(latestRx.ot_eye).toBe("L");
    expect(q("wizard-next").disabled).toBe(false);

    act(() => q("ot-outcome-referral").click());
    expect(latestRx).toEqual(expect.objectContaining({ ot_outcome: "referral", ot_eye: null }));
    expect(q("ot-eye-select")).toBeNull();
    expect(q("wizard-next").disabled).toBe(false);
  });

  test("IOL surgery cannot be chosen beside a specs line and the clash is named", async () => {
    renderLive({
      ...baseRx,
      prescribed_lines: ["specs_made", "ot"],
      specs_measurements: { ...baseRx.specs_measurements, r_sph: "-1.00", l_sph: "-1.25" },
    });
    await next(3);
    expect(q("ot-outcome-iol_surgery").disabled).toBe(true);
    expect(q("ot-outcome-blocked").textContent)
      .toBe("Spectacles to be made and IOL surgery cannot be on one prescription.");
    expect(q("ot-outcome-referral").disabled).toBe(false);
    act(() => q("ot-outcome-referral").click());
    expect(q("wizard-next").disabled).toBe(false);
  });

  test("vitals from the Hospital step are read back on review with the outcome", async () => {
    renderWizard({
      ...baseRx,
      prescribed_lines: ["ot"],
      ot_outcome: "iol_surgery",
      ot_eye: "R",
      ot_notes: "Left eye also prescribed",
      bp: "130/85",
      blood_sugar: "140",
    });
    await next(3);
    expect(q("summary-hospital").textContent).toBe("IOL surgery · Right eye · Left eye also prescribed");
    expect(q("summary-vitals").textContent).toBe("BP 130/85 · Blood sugar 140");
    expect(q("add-vitals-button")).toBeNull();
    expect(q("bp-input")).toBeNull();
  });

  test("a referral reads back as Hospital referral", async () => {
    renderWizard({ ...baseRx, prescribed_lines: ["ot"], ot_outcome: "referral" });
    await next(3);
    expect(q("summary-hospital").textContent).toBe("Hospital referral");
    expect(q("summary-vitals")).toBeNull();
  });

  test("vitals are hidden behind a control on review and never block completion", async () => {
    renderWizard({ ...baseRx, none_prescribed: true, full_transcription_confirmed: true });
    await next(2);
    expect(q("bp-input")).toBeNull();
    expect(q("complete-prescription-button").disabled).toBe(false);
    act(() => q("add-vitals-button").click());
    expect(q("bp-input")).not.toBeNull();
    expect(q("sugar-input")).not.toBeNull();
  });

  test("recorded vitals keep the panel open when the prescription is reopened", async () => {
    renderWizard({ ...baseRx, none_prescribed: true, bp: "120/80" });
    await next(2);
    expect(q("bp-input").value).toBe("120/80");
  });

  test("the review step reads back the medicines and power that were picked", async () => {
    renderWizard({
      ...baseRx,
      prescribed_lines: ["medicine", "specs_fixed"],
      prescribed_medicine_ids: ["med-2"],
      fixed_power_r: 2,
      fixed_power_l: -1.5,
      full_transcription_confirmed: true,
    });
    await next(4);
    expect(q("summary-medicines").textContent).toBe("Timolol");
    expect(q("summary-fixed-power").textContent).toBe("RE +2.00 · LE -1.50");
  });
});
