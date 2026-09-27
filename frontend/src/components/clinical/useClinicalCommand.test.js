import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { useClinicalCommand } from "./useClinicalCommand";
import api from "../../lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../../lib/api", () => {
  const actual = jest.requireActual("../../lib/api");
  return {
    __esModule: true,
    default: { post: jest.fn() },
    formatApiError: actual.formatApiError,
    errorPayload: actual.errorPayload,
  };
});

let container;
let root;
let command;

function Harness({ kind, patient }) {
  command = useClinicalCommand(kind, patient);
  return null;
}

const patient = (id = "reg-1", generation = 2) => ({ registration: { id, clinical_generation: generation } });
const refusal = (code) => ({ response: { status: 409, data: { detail: { code, message: `Refused: ${code}` } } } });
const ids = () => api.post.mock.calls.map(([, body]) => body.operation_id);

async function render(kind, data = patient()) {
  await act(async () => root.render(<Harness kind={kind} patient={data} />));
}

async function send(payload) {
  let outcome;
  await act(async () => {
    outcome = await command.send(payload).then((data) => ({ data }), (failure) => ({ failure }));
  });
  return outcome;
}

beforeEach(() => {
  container = document.createElement("div");
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
});

afterEach(() => {
  act(() => root.unmount());
});

test.each([
  ["complete", "/clinical/transcription/complete", "expected_generation"],
  ["undo", "/clinical/transcription/undo", "expected_generation"],
  ["correct", "/clinical/correction", "expected_generation"],
  ["issue", "/clinical/fulfilment", "reviewed_generation"],
])("%s posts to its endpoint with the patient's generation and an operation id", async (kind, url, field) => {
  api.post.mockResolvedValueOnce({ data: { ok: true } });
  await render(kind);
  const { data } = await send({ patient_id: "reg-1" });
  expect(data).toEqual({ ok: true });
  expect(api.post).toHaveBeenCalledWith(url, expect.objectContaining({
    patient_id: "reg-1", [field]: 2, operation_id: expect.any(String),
  }));
});

test.each(["complete", "undo", "correct", "issue"])("%s reuses its id for an unchanged payload and renews it for a changed one", async (kind) => {
  api.post.mockRejectedValue(new Error("Network Error"));
  await render(kind);
  await send({ answer: "a" });
  await send({ answer: "a" });
  await send({ answer: "b" });
  expect(ids()[1]).toBe(ids()[0]);
  expect(ids()[2]).not.toBe(ids()[0]);
});

test("a success clears the id so the next write is a new operation", async () => {
  api.post.mockResolvedValue({ data: {} });
  await render("issue");
  await send({ answer: "a" });
  await send({ answer: "a" });
  expect(ids()[1]).not.toBe(ids()[0]);
});

test("a patient change clears the id", async () => {
  api.post.mockRejectedValue(new Error("Network Error"));
  await render("issue", patient("reg-1"));
  await send({ answer: "a" });
  await render("issue", patient("reg-2"));
  await render("issue", patient("reg-1"));
  await send({ answer: "a" });
  expect(ids()[1]).not.toBe(ids()[0]);
});

test("reset clears the id", async () => {
  api.post.mockRejectedValue(new Error("Network Error"));
  await render("complete");
  await send({ answer: "a" });
  act(() => command.reset());
  await send({ answer: "a" });
  expect(ids()[1]).not.toBe(ids()[0]);
});

test.each(["STALE_GENERATION", "DRAFT_VERSION_CONFLICT", "OPERATION_SUPERSEDED", "STALE_REVIEW", "OPERATION_CONFLICT"])(
  "%s is a reload and clears the id",
  async (code) => {
    api.post.mockRejectedValue(refusal(code));
    await render("issue");
    const { failure } = await send({ answer: "a" });
    expect(failure).toEqual({ kind: "reload", message: `Refused: ${code}` });
    await send({ answer: "a" });
    expect(ids()[1]).not.toBe(ids()[0]);
  },
);

test("any other refusal is an error that keeps the id", async () => {
  api.post.mockRejectedValue(refusal("DAY_FULL"));
  await render("issue");
  const { failure } = await send({ answer: "a" });
  expect(failure).toEqual({ kind: "error", message: "Refused: DAY_FULL" });
  await send({ answer: "a" });
  expect(ids()[1]).toBe(ids()[0]);
});

test("the lookup's generation wins over the registration's", async () => {
  api.post.mockResolvedValueOnce({ data: {} });
  await render("complete", { clinical_generation: 4, registration: { id: "reg-1", clinical_generation: 3 } });
  await send({ answer: "a" });
  expect(api.post.mock.calls[0][1].expected_generation).toBe(4);
});

test("a patient without a generation sends 0", async () => {
  api.post.mockResolvedValueOnce({ data: {} });
  await render("issue", { registration: { id: "reg-1" } });
  await send({ answer: "a" });
  expect(api.post.mock.calls[0][1].reviewed_generation).toBe(0);
});
