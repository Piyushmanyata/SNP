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
  api.post.mockResolvedValue({ data: { correction_id: "c-1" } });
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
  act(() => {
    const eye = container.querySelector('[data-testid="ot-eye-select"]');
    eye.value = "L";
    eye.dispatchEvent(new Event("change", { bubbles: true }));
    setInput(container.querySelector('[data-testid="ot-notes-input"]'), "Left eye first as prescribed");
    setInput(container.querySelector('[data-testid="correction-reason-input"]'), "  Completed from doctor's paper prescription  ");
  });
  await act(async () => {
    container.querySelector('[data-testid="save-transcription-button"]').click();
  });
  expect(api.post).toHaveBeenCalledWith("/clinical/correction", expect.objectContaining({
    transcription_id: "tx-1",
    patient_id: "reg-1",
    reason: "Completed from doctor's paper prescription",
    changes: { ot_eye: "L", ot_notes: "Left eye first as prescribed" },
    expected_generation: 1,
    prescribed_lines: ["medicine", "ot"],
  }));
  expect(api.post.mock.calls[0][1].operation_id).toEqual(expect.any(String));
  expect(onDone).toHaveBeenCalledTimes(1);
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
