import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { useDeskSession } from "./useDeskSession";
import api from "../../lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../../lib/api", () => {
  const actual = jest.requireActual("../../lib/api");
  return {
    __esModule: true,
    default: { get: jest.fn(), post: jest.fn() },
    formatApiError: actual.formatApiError,
    errorPayload: actual.errorPayload,
  };
});

const REG = { id: "p-1", reg_no: "101", full_name: "Asha Devi", arrived_at: "2026-10-05T03:30:00Z" };
const NEXT = { id: "p-2", reg_no: "102", full_name: "Ravi Kumar", arrived_at: "2026-10-05T03:31:00Z" };

let container;
let root;
let session;

function Harness(props) {
  session = useDeskSession({ onCreated: jest.fn(), printingOpen: true, operatingDayId: "day-1", ...props });
  return null;
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  container = document.createElement("div");
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
});

afterEach(() => {
  act(() => root.unmount());
});

async function mount(props = {}) {
  await act(async () => root.render(<Harness printPrescription={jest.fn()} {...props} />));
}

const state = () => session[0];
const actions = () => session[1];

test("a lookup reply that lands after a newer lookup is dropped", async () => {
  const slow = deferred();
  api.post.mockReturnValueOnce(slow.promise).mockResolvedValueOnce({ data: { registration: NEXT } });
  await mount();
  let first;
  await act(async () => { first = actions().lookupCode("snp:OLD"); });
  await act(async () => { await actions().lookupCode("snp:NEW"); });
  await act(async () => { slow.resolve({ data: { registration: REG } }); await first; });
  expect(state().found.reg).toBe(NEXT);
});

test("a second Print while one is running starts nothing", async () => {
  const printing = deferred();
  const printPrescription = jest.fn(() => printing.promise);
  api.get.mockResolvedValue({ data: { prescription: { reg_no: "101" } } });
  await mount({ printPrescription });
  let first;
  await act(async () => { first = actions().print(REG); });
  await act(async () => { await actions().print(REG); });
  await act(async () => { printing.resolve(); await first; });
  expect(printPrescription).toHaveBeenCalledTimes(1);
  expect(api.get).toHaveBeenCalledTimes(1);
  expect(state().paperCheck).toEqual(expect.objectContaining({ reg: REG, busy: false }));
});

test("a print whose patient changed while fetching the sheet never opens a Paper check", async () => {
  const sheet = deferred();
  const printPrescription = jest.fn();
  api.get.mockReturnValueOnce(sheet.promise);
  api.post.mockResolvedValueOnce({ data: { registration: NEXT } });
  await mount({ printPrescription });
  let printing;
  await act(async () => { printing = actions().print(REG); });
  await act(async () => { await actions().lookupCode("snp:NEXT"); });
  await act(async () => { sheet.resolve({ data: { prescription: { reg_no: "101" } } }); await printing; });
  expect(printPrescription).not.toHaveBeenCalled();
  expect(state().paperCheck).toBeNull();
});

test("a reply that lands after unmount changes nothing", async () => {
  const slow = deferred();
  api.post.mockReturnValueOnce(slow.promise);
  await mount();
  let pending;
  await act(async () => { pending = actions().lookupCode("snp:OLD"); });
  const before = state();
  act(() => root.unmount());
  await act(async () => { slow.resolve({ data: { registration: REG } }); await pending; });
  expect(state()).toBe(before);
  root = ReactDOM.createRoot(container);
});

test("Printed — next patient stamps once and moves the cursor to the USB box", async () => {
  const box = document.createElement("textarea");
  box.setAttribute("data-usb-box", "");
  document.body.appendChild(box);
  api.get.mockResolvedValue({ data: { prescription: { reg_no: "101", sheet_stamp: "s-1" } } });
  api.post.mockResolvedValueOnce({ data: { registration: REG } });
  await mount();
  await act(async () => { await actions().print(REG); });
  await act(async () => { await actions().confirmPaper(); });
  expect(api.post).toHaveBeenCalledWith("/desk/print/p-1", { sheet_stamp: "s-1" });
  expect(state().banner).toBe("Printed #101 — Asha Devi. Next patient.");
  expect(document.activeElement).toBe(box);
  box.remove();
});

test("a flip of printingOpen or operatingDayId clears the found patient; unchanged props and the first render do not", async () => {
  api.post.mockResolvedValue({ data: { registration: REG } });
  await mount();
  expect(state().found).toBeNull();
  await act(async () => { await actions().lookupCode("snp:ONE"); });
  expect(state().found.reg).toBe(REG);
  await mount();
  expect(state().found.reg).toBe(REG);
  await mount({ printingOpen: false });
  expect(state().found).toBeNull();
  await act(async () => { await actions().lookupCode("snp:TWO"); });
  expect(state().found.reg).toBe(REG);
  await mount({ printingOpen: false });
  expect(state().found.reg).toBe(REG);
  await mount({ printingOpen: false, operatingDayId: "day-2" });
  expect(state().found).toBeNull();
});

test("a flip of the Print window clears the search results and keeps a Paper check that is open", async () => {
  api.get.mockImplementation((url) => Promise.resolve({
    data: url.startsWith("/patients/search") ? { results: [NEXT] } : { prescription: { reg_no: "101", sheet_stamp: "s-1" } },
  }));
  api.post.mockResolvedValueOnce({ data: { registration: REG } });
  await mount();
  await act(async () => { actions().setFindVal("Ravi"); });
  await act(async () => { await actions().find(); });
  expect(state().searchResults).toEqual([NEXT]);
  await act(async () => { await actions().print(REG); });
  expect(state().paperCheck).not.toBeNull();

  await mount({ printingOpen: false });
  expect(state().searchResults).toBeNull();
  expect(state().paperCheck).not.toBeNull();
  await act(async () => { await actions().confirmPaper(); });
  expect(api.post).toHaveBeenCalledWith("/desk/print/p-1", { sheet_stamp: "s-1" });
  expect(state().banner).toBe("Printed #101 — Asha Devi. Next patient.");
});

test("Print again fetches a fresh sheet, and the Paper check sends that sheet's stamp", async () => {
  api.get
    .mockResolvedValueOnce({ data: { prescription: { reg_no: "101", sheet_stamp: "s-1" } } })
    .mockResolvedValueOnce({ data: { prescription: { reg_no: "101", sheet_stamp: "s-2" } } });
  api.post.mockResolvedValueOnce({ data: { registration: REG } });
  await mount();
  await act(async () => { await actions().print(REG); });
  await act(async () => { await actions().printAgain(); });
  await act(async () => { await actions().confirmPaper(); });
  expect(api.get).toHaveBeenCalledTimes(2);
  expect(api.post).toHaveBeenCalledWith("/desk/print/p-1", { sheet_stamp: "s-2" });
});

const WALK_IN_CARD = { full_name: "Asha Devi", age: 42, gender: "F", address: "Sikar", aadhaar_last4: "8888", dob: "1984-05-12" };
const registerBodies = () => api.post.mock.calls.filter(([url]) => url === "/register").map(([, body]) => body);
const requestIds = () => registerBodies().map((body) => body.registration_request_id);

async function scanWalkIn(phone = "9876500001") {
  api.post.mockResolvedValueOnce({ data: { outcome: "no_match", card: WALK_IN_CARD } });
  await act(async () => { await actions().resolveDoorScan("CARD-A"); });
  await act(async () => actions().setDoorPhone(phone));
}

async function walkIn() {
  await act(async () => { await actions().submitDoorWalkIn(); });
}

test("a walk-in registers the card at the door on the operating day", async () => {
  const onCreated = jest.fn();
  await mount({ onCreated });
  await scanWalkIn();
  api.post.mockResolvedValueOnce({ data: { registration: REG, created: true } });
  await walkIn();
  expect(registerBodies()[0]).toEqual(expect.objectContaining({
    full_name: "Asha Devi", phone: "9876500001", aadhaar_scanned: true, qr_payload: "CARD-A",
    camp_day_id: "day-1", at_door: true, review_confirmed_id: null, different_person: false,
  }));
  expect(onCreated).toHaveBeenCalledWith({ registration: REG, created: true });
  expect(state().scanResult.registration).toBe(REG);
});

test("a walk-in whose phone is edited after a failure sends a new id, and an unchanged retry reuses it", async () => {
  await mount();
  await scanWalkIn();
  api.post.mockRejectedValue(new Error("Network Error"));
  await walkIn();
  await walkIn();
  await act(async () => actions().setDoorPhone("9876500009"));
  await walkIn();
  await walkIn();
  const [first, retry, edited, editedRetry] = requestIds();
  expect(retry).toBe(first);
  expect(edited).not.toBe(first);
  expect(editedRetry).toBe(edited);
  expect(state().error).toBe("Network Error");
  expect(state().busy).toBe(false);
});

test("a walk-in request conflict points to search", async () => {
  await mount();
  await scanWalkIn();
  api.post.mockRejectedValue({ response: { status: 409, data: { detail: { code: "REGISTRATION_REQUEST_CONFLICT", message: "Request id reused." } } } });
  await walkIn();
  expect(state().error).toBe("Saved earlier. Search for the patient.");
});

test("a walk-in with no operating day registers nobody", async () => {
  await mount({ operatingDayId: "" });
  await scanWalkIn();
  await walkIn();
  expect(registerBodies()).toHaveLength(0);
  expect(state().error).toBe("No operating camp day. Use Pre-registration.");
});

test("a second Register tap in the same tick sends one request", async () => {
  const saving = deferred();
  await mount();
  await scanWalkIn();
  api.post.mockReturnValueOnce(saving.promise);
  let first;
  let second;
  await act(async () => {
    first = actions().submitDoorWalkIn();
    second = actions().submitDoorWalkIn();
    await second;
  });
  expect(registerBodies()).toHaveLength(1);
  await act(async () => { saving.resolve({ data: { registration: REG, created: true } }); await first; });
  expect(registerBodies()).toHaveLength(1);
  expect(state().busy).toBe(false);
});

test("scanning the same card again after a failed walk-in sends a new id", async () => {
  await mount();
  await scanWalkIn();
  api.post.mockRejectedValueOnce(new Error("Network Error"));
  await walkIn();
  await scanWalkIn();
  api.post.mockRejectedValueOnce(new Error("Network Error"));
  await walkIn();
  const [first, second] = requestIds();
  expect(second).not.toBe(first);
});
