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

test("specs_measurements submits an object and other fields submit a string", async () => {
  const onDone = jest.fn();
  await act(async () => {
    root.render(<CorrectionForm transcriptionId="tx-1" onDone={onDone} />);
  });

  setInput(container.querySelector('[data-testid="correction-reason-input"]'), "missed power");
  await act(async () => {
    container.querySelector('[data-testid="correction-submit-button"]').click();
  });
  expect(api.post).toHaveBeenCalledWith("/clinical/correction", {
    transcription_id: "tx-1",
    reason: "missed power",
    changes: { remarks: "" },
  });

  const select = container.querySelector('[data-testid="correction-field-select"]');
  act(() => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
    setter.call(select, "specs_measurements");
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  setInput(container.querySelector('[data-testid="specs-r_sph"]'), "-1.00");
  setInput(container.querySelector('[data-testid="specs-l_sph"]'), "-1.25");
  await act(async () => {
    container.querySelector('[data-testid="correction-submit-button"]').click();
  });
  const body = api.post.mock.calls[1][1];
  expect(body.changes.specs_measurements).toEqual({
    r_sph: "-1.00", r_cyl: "", r_axis: "", l_sph: "-1.25", l_cyl: "", l_axis: "", add: "",
  });
});
