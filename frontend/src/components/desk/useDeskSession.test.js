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
