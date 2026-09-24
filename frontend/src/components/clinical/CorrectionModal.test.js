import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { CorrectionForm } from "./CorrectionModal";
import api from "../../lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../../lib/api", () => {
  const actual = jest.requireActual("../../lib/api");
  return {
    __esModule: true,
    default: { post: jest.fn(), get: jest.fn() },
    formatApiError: actual.formatApiError,
  };
});

let container;
let root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  api.post.mockResolvedValue({ data: {} });
});

afterEach(() => {
  act(() => { root.unmount(); });
  container.remove();
});

function setInput(el, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

test("a surgery operator completes a locked prescription after medicine was issued", async () => {
  const onDone = jest.fn();
  await act(async () => {
    root.render(<CorrectionForm
      transcription={{ id: "tx-1", locked: true, diagnosis_options: ["Cataract"], remarks: "Medicine issued", ot_eye: "", ot_notes: "" }}
      line="ot"
      diagOpts={["Cataract", "Glaucoma"]}
      expectedGeneration={1}
      patientId="reg-1"
      prescribedLines={["medicine"]}
      onDone={onDone}
    />);
  });
  expect(container.querySelector('[data-testid="remarks-input"]').value).toBe("Medicine issued");
  expect(container.querySelector('[data-testid="diagnosis-opt-cataract"]').getAttribute("aria-pressed")).toBe("true");
  expect(container.querySelector('[data-testid="ot-procedure-input"]')).toBeNull();
  act(() => {
    setInput(container.querySelector('[data-testid="correction-reason-input"]'), "  Completed from doctor's paper prescription  ");
  });
  expect(container.querySelector('[data-testid="save-transcription-button"]').disabled).toBe(true);
  act(() => container.querySelector('[data-testid="ot-outcome-iol_surgery"]').click());
  const eye = container.querySelector('[data-testid="ot-eye-select"]');
  expect([...eye.options].map((o) => o.value)).toEqual(["", "R", "L"]);
  act(() => setInput(container.querySelector('[data-testid="ot-notes-input"]'), "Left eye first as prescribed"));
  expect(container.querySelector('[data-testid="save-transcription-button"]').disabled).toBe(true);
  act(() => {
    eye.value = "L";
    eye.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await act(async () => {
    container.querySelector('[data-testid="save-transcription-button"]').click();
  });
  expect(api.post).toHaveBeenCalledWith("/clinical/correction", expect.objectContaining({
    transcription_id: "tx-1",
    patient_id: "reg-1",
    reason: "Completed from doctor's paper prescription",
    changes: { ot_outcome: "iol_surgery", ot_eye: "L", ot_notes: "Left eye first as prescribed" },
    expected_generation: 1,
    prescribed_lines: ["medicine", "ot"],
  }));
  expect(api.post.mock.calls[0][1].operation_id).toEqual(expect.any(String));
  expect(onDone).toHaveBeenCalledTimes(1);
});

test("a declined IOL surgery becomes spectacles only once the Hospital line is removed", async () => {
  await act(async () => root.render(<CorrectionForm
    transcription={{ id: "tx-4", ot_outcome: "iol_surgery", ot_eye: "R", ot_notes: "" }}
    line="specs_made"
    prescribedLines={["ot"]}
    onDone={jest.fn()}
  />));
  const save = () => container.querySelector('[data-testid="save-transcription-button"]');
  expect(container.querySelector('[role="alert"]')).toBeNull();
  expect(container.querySelector('[data-testid="prescribed-specs_made"]').checked).toBe(false);
  expect(container.querySelector('[data-testid="prescribed-specs_made"]').disabled).toBe(true);

  act(() => container.querySelector('[data-testid="prescribed-ot"]').click());
  act(() => container.querySelector('[data-testid="prescribed-specs_made"]').click());
  act(() => {
    setInput(container.querySelector('[data-testid="specs-r_sph"]'), "-1.00");
    setInput(container.querySelector('[data-testid="specs-l_sph"]'), "-1.25");
    setInput(container.querySelector('[data-testid="correction-reason-input"]'), "Patient declined surgery, wants spectacles");
  });
  expect(container.querySelector('[role="alert"]')).toBeNull();
  expect(container.querySelector('[data-testid="ot-outcome-iol_surgery"]')).toBeNull();
  expect(save().disabled).toBe(false);
  await act(async () => save().click());
  const body = api.post.mock.calls[0][1];
  expect(body.prescribed_lines).toEqual(["specs_made"]);
  expect(body.changes).toEqual(expect.objectContaining({ ot_outcome: null, ot_eye: null }));
});

test("a correction that only changes the ticked lines can be saved", async () => {
  await act(async () => root.render(<CorrectionForm
    transcription={{ id: "tx-6", prescribed_medicines: [], specs_measurements: { r_sph: "-1.00", l_sph: "-1.25" } }}
    line="specs_made"
    prescribedLines={["medicine", "specs_made"]}
    onDone={jest.fn()}
  />));
  act(() => {
    container.querySelector('[data-testid="prescribed-medicine"]').click();
    setInput(container.querySelector('[data-testid="correction-reason-input"]'), "Medicine was not written");
  });
  const save = container.querySelector('[data-testid="save-transcription-button"]');
  expect(save.disabled).toBe(false);
  await act(async () => save.click());
  expect(api.post.mock.calls[0][1].prescribed_lines).toEqual(["specs_made"]);
});

test("a correction names every line that clashes", async () => {
  await act(async () => root.render(<CorrectionForm
    transcription={{ id: "tx-7", ot_outcome: "iol_surgery", ot_eye: "R" }}
    line="medicine"
    prescribedLines={["specs_fixed", "specs_made", "ot"]}
    onDone={jest.fn()}
  />));
  expect(container.querySelector('[role="alert"]').textContent)
    .toBe("Fixed-power specs, Spectacles to be made and IOL surgery cannot be on one prescription.");
});

test("choosing Hospital referral in a correction drops the eye", async () => {
  await act(async () => root.render(<CorrectionForm
    transcription={{ id: "tx-5", ot_outcome: "iol_surgery", ot_eye: "L" }}
    line="ot"
    prescribedLines={["ot", "medicine"]}
    onDone={jest.fn()}
  />));
  act(() => {
    container.querySelector('[data-testid="ot-outcome-referral"]').click();
    setInput(container.querySelector('[data-testid="correction-reason-input"]'), "Doctor wrote referral");
  });
  expect(container.querySelector('[data-testid="ot-eye-select"]')).toBeNull();
  await act(async () => container.querySelector('[data-testid="save-transcription-button"]').click());
  expect(api.post.mock.calls[0][1]).toEqual(expect.objectContaining({
    changes: { ot_outcome: "referral", ot_eye: null },
    prescribed_lines: ["ot", "medicine"],
  }));
});

test("corrections preserve existing powers and diagnosis when changing other fields", async () => {
  await act(async () => root.render(<CorrectionForm
    transcription={{ id: "tx-2", diagnosis_options: ["Cataract"], specs_measurements: { r_sph: "-1.00", l_sph: "-1.25", add: "+2.00" } }}
    diagOpts={["Cataract", "Glaucoma"]}
    line="specs_made"
    onDone={jest.fn()}
  />));
  expect(container.querySelector('[data-testid="specs-l_sph"]').value).toBe("-1.25");
  act(() => {
    setInput(container.querySelector('[data-testid="specs-r_sph"]'), "-1.50");
    container.querySelector('[data-testid="diagnosis-opt-glaucoma"]').click();
    setInput(container.querySelector('[data-testid="correction-reason-input"]'), "Corrected from paper");
  });
  await act(async () => container.querySelector('[data-testid="save-transcription-button"]').click());
  const body = api.post.mock.calls[0][1];
  expect(body.changes.specs_measurements).toEqual({
    r_sph: "-1.50", r_cyl: "", r_axis: "", l_sph: "-1.25", l_cyl: "", l_axis: "", add: "+2.00",
  });
  expect(body.changes.diagnosis_options).toEqual(["Cataract", "Glaucoma"]);
  expect(body.changes).not.toHaveProperty("remarks");
});

test("a failed correction is retried under the same operation id only while the request is unchanged", async () => {
  await act(async () => root.render(<CorrectionForm transcription={{ id: "tx-8" }} onDone={jest.fn()} />));
  act(() => {
    setInput(container.querySelector('[data-testid="remarks-input"]'), "Changed");
    setInput(container.querySelector('[data-testid="correction-reason-input"]'), "From paper");
  });
  const save = () => act(async () => container.querySelector('[data-testid="save-transcription-button"]').click());
  api.post.mockRejectedValueOnce(new Error("Network Error"));
  await save();
  api.post.mockRejectedValueOnce(new Error("Network Error"));
  await save();
  act(() => setInput(container.querySelector('[data-testid="correction-reason-input"]'), "From the doctor's paper"));
  await save();
  const ids = api.post.mock.calls.map(([, body]) => body.operation_id);
  expect(ids[1]).toBe(ids[0]);
  expect(ids[2]).not.toBe(ids[0]);
});

test("unchanged prescriptions and blank audit reasons cannot be submitted", async () => {
  await act(async () => root.render(<CorrectionForm transcription={{ id: "tx-3" }} onDone={jest.fn()} />));
  act(() => setInput(container.querySelector('[data-testid="correction-reason-input"]'), "Reason only"));
  expect(container.querySelector('[data-testid="save-transcription-button"]').disabled).toBe(true);
  act(() => {
    setInput(container.querySelector('[data-testid="remarks-input"]'), "Changed");
    setInput(container.querySelector('[data-testid="correction-reason-input"]'), "   ");
  });
  expect(container.querySelector('[data-testid="save-transcription-button"]').disabled).toBe(true);
  expect(api.post).not.toHaveBeenCalled();
});

test("a tap on the Medicines or Fixed power label selects nothing", async () => {
  await act(async () => {
    root.render(<CorrectionForm
      transcription={{ id: "tx-1", locked: true, diagnosis_options: [] }}
      line="doctor_rx"
      diagOpts={["Cataract"]}
      medicines={[{ id: "med-1", name: "Moxifloxacin", active: true }]}
      powers={[{ id: "p1", value: -1.5, label: "-1.50", active: true }]}
      expectedGeneration={1}
      patientId="reg-1"
      prescribedLines={["medicine", "specs_fixed"]}
      onDone={jest.fn()}
    />);
  });
  const label = (inner) => document.getElementById(inner.closest('[role="group"]').getAttribute("aria-labelledby"));
  act(() => label(container.querySelector('[data-testid="medicine-picker"]')).click());
  act(() => label(container.querySelector('[data-testid="fixed-power-both-minus"]')).click());
  expect(container.querySelector('[data-testid="medicine-opt-med-1"]').getAttribute("aria-pressed")).toBe("false");
  expect(container.querySelector('[data-testid="fixed-power-both--1.5"]').getAttribute("aria-pressed")).toBe("false");
});
