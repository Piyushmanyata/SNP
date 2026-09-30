import React, { act } from "react";
import ReactDOM from "react-dom/client";
import api from "../../lib/api";
import { useRegistrationRequest } from "../../lib/useRegistrationRequest";
import { hasAge, registerPatient, registrationBody, registrationError, registrationFailure } from "./register";
import { EMPTY_REASON } from "./ManualReason";

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

const CARD = "AADHAAR|Sunita Devi|F|1975-06-14|1234|12 Station Road";
const FORM = {
  full_name: "Sunita Devi", age: 51, phone: "+91 98765 00001", gender: "F",
  address: "12 Station Road", aadhaar_last4: "1234", dob: "1975-06-14",
};
const SCANNED = { form: FORM, qrPayload: CARD, dayId: "day-1", atDoor: false };
const TYPED = {
  form: { ...FORM, aadhaar_last4: "", dob: "", address: "" },
  qrPayload: "",
  dayId: "day-1",
  reason: { code: "other", note: "  Card is with her son  " },
  atDoor: false,
};
const refusal = (detail) => ({ response: { status: 409, data: { detail } } });
const sentIds = () => api.post.mock.calls.map(([, body]) => body.registration_request_id);

let container;
let root;
let request;

function Harness() {
  request = useRegistrationRequest();
  return null;
}

beforeEach(async () => {
  container = document.createElement("div");
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  await act(async () => root.render(<Harness />));
});

afterEach(() => {
  act(() => root.unmount());
});

async function register(args) {
  let outcome;
  await act(async () => {
    outcome = await registerPatient(request, args).then((data) => ({ data }), (failure) => ({ failure }));
  });
  return outcome;
}

test("hasAge accepts zero and refuses blank", () => {
  expect([0, "0", 42, "42"].map(hasAge)).toEqual([true, true, true, true]);
  expect(["", null, undefined].map(hasAge)).toEqual([false, false, false]);
});

test("a scanned body carries the card and no manual reason, and leaves the id and both confirmations out", () => {
  const body = registrationBody(SCANNED);
  expect(body).toEqual({
    full_name: "Sunita Devi", age: 51, phone: "9876500001", gender: "F", address: "12 Station Road",
    aadhaar_last4: "1234", dob: "1975-06-14", aadhaar_scanned: true, qr_payload: CARD,
    camp_day_id: "day-1", manual_reason: null, manual_note: null, at_door: false,
  });
  expect(body).not.toHaveProperty("registration_request_id");
  expect(body).not.toHaveProperty("review_confirmed_id");
  expect(body).not.toHaveProperty("different_person");
});

test("a typed body claims no scan and carries the trimmed reason", () => {
  expect(registrationBody(TYPED)).toEqual(expect.objectContaining({
    aadhaar_scanned: false, qr_payload: null, aadhaar_last4: null, dob: null, address: null,
    manual_reason: "other", manual_note: "Card is with her son",
  }));
});

test("a blank age is null and an age of zero is kept", () => {
  expect(registrationBody({ ...SCANNED, form: { ...FORM, age: "" } }).age).toBeNull();
  expect(registrationBody({ ...SCANNED, form: { ...FORM, age: "0" } }).age).toBe(0);
});

test("a door body says so, with no reason when the card is scanned", () => {
  expect(registrationBody({ ...SCANNED, atDoor: true, reason: EMPTY_REASON })).toEqual(expect.objectContaining({
    at_door: true, manual_reason: null,
  }));
});

test("registerPatient posts the body with the request id and both confirmations, and returns the data", async () => {
  api.post.mockResolvedValueOnce({ data: { registration: { id: "p-1" } } });
  const { data } = await register({ ...SCANNED, reviewConfirmedId: "p-3", differentPerson: true });
  expect(data).toEqual({ registration: { id: "p-1" } });
  expect(api.post).toHaveBeenCalledWith("/register", {
    ...registrationBody(SCANNED),
    registration_request_id: expect.any(String),
    review_confirmed_id: "p-3",
    different_person: true,
  });
});

test("registerPatient sends no confirmation unless asked", async () => {
  api.post.mockResolvedValueOnce({ data: {} });
  await register(SCANNED);
  expect(api.post.mock.calls[0][1]).toEqual(expect.objectContaining({ review_confirmed_id: null, different_person: false }));
});

test.each([
  ["phone", { form: { ...FORM, phone: "9876500009" } }],
  ["name", { form: { ...FORM, full_name: "Sunita Bai" } }],
  ["camp day", { dayId: "day-2" }],
  ["card", { qrPayload: `${CARD}x` }],
])("a changed %s gives a new id", async (_name, change) => {
  api.post.mockRejectedValue(new Error("Network Error"));
  await register(SCANNED);
  await register({ ...SCANNED, ...change });
  expect(sentIds()[1]).not.toBe(sentIds()[0]);
});

test("a typed registration gets a new id when the reason or the gender changes", async () => {
  api.post.mockRejectedValue(new Error("Network Error"));
  await register(TYPED);
  await register({ ...TYPED, reason: { code: "no_card", note: "" } });
  await register({ ...TYPED, reason: { code: "no_card", note: "" }, form: { ...TYPED.form, gender: "M" } });
  expect(new Set(sentIds()).size).toBe(3);
});

test.each([
  ["MISMATCH_REVIEW_REQUIRED", { code: "MISMATCH_REVIEW_REQUIRED", registration: { id: "p-3" }, diff: [] },
    { kind: "review", review: { code: "MISMATCH_REVIEW_REQUIRED", registration: { id: "p-3" }, diff: [] } }],
  ["LOOKALIKES", { code: "LOOKALIKES", registrations: [{ id: "p-3" }] },
    { kind: "lookalikes", lookalikes: [{ id: "p-3" }] }],
  ["DUPLICATE_IN_CAMP", { code: "DUPLICATE_IN_CAMP", registration: { reg_no: 7 } },
    { kind: "error", message: "Already registered as #7. Find them below and print." }],
  ["AMBIGUOUS_MANUAL_ENTRY", { code: "AMBIGUOUS_MANUAL_ENTRY", registrations: [{ reg_no: 3 }, { reg_no: 5 }] },
    { kind: "error", message: "Multiple Manual entries match (#3, #5). Scan the card at the door to pick one." }],
  ["REGISTRATION_REQUEST_CONFLICT", { code: "REGISTRATION_REQUEST_CONFLICT", message: "Request id reused." },
    { kind: "error", message: "Saved earlier. Search for the patient." }],
  ["any other refusal", { code: "CAMP_DAY_FULL", message: "This camp day is full." },
    { kind: "error", message: "This camp day is full." }],
])("%s is routed by registrationFailure", (_name, detail, failure) => {
  expect(registrationFailure(refusal(detail))).toEqual(failure);
});

test("a network error is an error with its own message", () => {
  expect(registrationFailure(new Error("Network Error"))).toEqual({ kind: "error", message: "Network Error" });
  expect(registrationError(new Error("Network Error"))).toBe("Network Error");
});
