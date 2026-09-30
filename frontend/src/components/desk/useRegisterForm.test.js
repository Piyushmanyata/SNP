import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { useRegisterForm } from "./useRegisterForm";
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

const CARD = {
  full_name: "Sunita Devi", age: 51, gender: "F", address: "12 Station Road", aadhaar_last4: "1234", dob: "1975-06-14",
};
const PAYLOAD = "AADHAAR|Sunita Devi|F|1975-06-14|1234|12 Station Road";
const DAYS = [{ id: "day-1", is_today: true }, { id: "day-2", is_today: false }];
const REG = { id: "p-7", reg_no: "107", full_name: "Sunita Devi" };
const refusal = (detail) => ({ response: { status: 409, data: { detail } } });

let container;
let root;
let session;
let props;

function Harness(current) {
  session = useRegisterForm(current);
  return null;
}

const state = () => session[0];
const actions = () => session[1];

function freshProps(overrides = {}) {
  return {
    open: true, atDoor: false, doorDayId: "day-9", days: DAYS, initialPayload: "",
    onClose: jest.fn(), onDone: jest.fn(), onRegistered: jest.fn(), setBanner: jest.fn(),
    ...overrides,
  };
}

async function mount(overrides) {
  props = freshProps(overrides);
  await act(async () => root.render(<Harness {...props} />));
}

async function update(overrides) {
  props = { ...props, ...overrides };
  await act(async () => root.render(<Harness {...props} />));
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function routes(handlers) {
  api.post.mockImplementation((url, body) => (handlers[url] ? handlers[url](body) : Promise.resolve({ data: {} })));
}

const decodesCard = () => Promise.resolve({ data: { outcome: "card", data: CARD } });
const registered = () => Promise.resolve({ data: { registration: REG, created: true } });
const lost = () => Promise.reject(new Error("Network Error"));
const registers = () => api.post.mock.calls.filter(([url]) => url === "/register").map(([, body]) => body);
const ids = () => registers().map((body) => body.registration_request_id);

async function fireBurst(text) {
  let t = Number(performance.now()) || 0;
  const spy = jest.spyOn(performance, "now").mockImplementation(() => t);
  await act(async () => {
    for (const ch of text) {
      t += 10;
      document.dispatchEvent(new KeyboardEvent("keydown", { key: ch, bubbles: true, cancelable: true }));
    }
    t += 10;
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
  });
  spy.mockRestore();
}

async function scan(phone = "9876500001") {
  await act(async () => actions().onScanned(CARD, PAYLOAD));
  await act(async () => actions().setField("phone", phone));
}

async function save(options) {
  await act(async () => { await actions().save(options); });
}

beforeEach(() => {
  container = document.createElement("div");
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  api.post.mockReset();
});

afterEach(() => {
  act(() => root.unmount());
});

test("a failed save then a retry with no edit reuses the id, and Register and next gives the next patient a new one", async () => {
  await mount();
  routes({ "/register": lost });
  await scan();
  await save();
  await save();
  routes({ "/register": registered });
  await save({ next: true });
  await scan();
  await save({ next: true });
  expect(ids()[1]).toBe(ids()[0]);
  expect(ids()[2]).toBe(ids()[0]);
  expect(ids()[3]).not.toBe(ids()[2]);
  expect(props.onClose).not.toHaveBeenCalled();
  expect(state().form.full_name).toBe("");
});

test("editing the phone after a failed save sends a new id", async () => {
  await mount();
  routes({ "/register": lost });
  await scan();
  await save();
  await act(async () => actions().setField("phone", "9876500009"));
  await save();
  expect(ids()[1]).not.toBe(ids()[0]);
});

test("Mismatch review confirm reuses the id of the attempt that raised it", async () => {
  await mount();
  const review = { code: "MISMATCH_REVIEW_REQUIRED", registration: { id: "p-3" }, diff: [] };
  routes({ "/register": (body) => (body.review_confirmed_id ? registered() : Promise.reject(refusal(review))) });
  await scan();
  await save();
  expect(state().review).toEqual(review);
  await save({ reviewConfirmedId: "p-3" });
  expect(registers()[1].review_confirmed_id).toBe("p-3");
  expect(ids()[1]).toBe(ids()[0]);
  expect(props.onClose).toHaveBeenCalledTimes(1);
});

test("Different person on a Lookalike reuses the id too", async () => {
  await mount();
  const lookalikes = { code: "LOOKALIKES", registrations: [{ id: "p-3", reg_no: "103" }] };
  routes({ "/register": (body) => (body.different_person ? registered() : Promise.reject(refusal(lookalikes))) });
  await act(async () => actions().toggleManual());
  await act(async () => actions().chooseReason({ code: "no_card", note: "" }));
  await act(async () => { actions().setField("gender", "F"); actions().setField("full_name", "Ram Kumar"); actions().setField("age", "40"); actions().setField("phone", "9876500001"); });
  await save();
  expect(state().lookalikeRows).toEqual(lookalikes.registrations);
  await save({ differentPerson: true });
  expect(registers()[1].different_person).toBe(true);
  expect(ids()[1]).toBe(ids()[0]);
});

test("a registration request conflict points to search and gives the next try a new id", async () => {
  await mount();
  routes({ "/register": () => Promise.reject(refusal({ code: "REGISTRATION_REQUEST_CONFLICT", message: "Request id reused." })) });
  await scan();
  await save();
  expect(state().error).toBe("Saved earlier. Search for the patient.");
  await save();
  expect(ids()[1]).not.toBe(ids()[0]);
});

test("reading the same card again after a failed save gives a new id on the camera path", async () => {
  await mount();
  routes({ "/register": lost });
  await scan();
  await save();
  await scan();
  await save();
  expect(ids()[1]).not.toBe(ids()[0]);
});

test("reading the same card again after a failed save gives a new id on the USB path", async () => {
  await mount();
  routes({ "/register": lost, "/aadhaar/decode": decodesCard });
  await scan();
  await save();
  await fireBurst(PAYLOAD);
  await act(async () => actions().setField("phone", "9876500001"));
  await save();
  expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", { payload: PAYLOAD });
  expect(state().qrPayload).toBe(PAYLOAD);
  expect(ids()[1]).not.toBe(ids()[0]);
});

test("reopening the modal gives a new id and an empty form", async () => {
  routes({ "/register": lost });
  await mount({ open: false });
  const typeAndSave = async () => {
    await act(async () => actions().toggleManual());
    await act(async () => actions().chooseReason({ code: "no_card", note: "" }));
    await act(async () => {
      actions().setField("gender", "F");
      actions().setField("full_name", "Kamla Bai");
      actions().setField("age", "62");
      actions().setField("phone", "9876500002");
    });
    await save();
  };
  await update({ open: true });
  await typeAndSave();
  await update({ open: false });
  await update({ open: true });
  expect(state().form).toEqual(expect.objectContaining({ full_name: "", phone: "" }));
  expect(state().manualMode).toBe(false);
  expect(state().error).toBe("");
  await typeAndSave();
  expect({ ...registers()[1], registration_request_id: null }).toEqual({ ...registers()[0], registration_request_id: null });
  expect(ids()[1]).not.toBe(ids()[0]);
});

test("a decode that lands after the manual toggle changes nothing", async () => {
  await mount();
  const decode = deferred();
  routes({ "/aadhaar/decode": () => decode.promise });
  await fireBurst(PAYLOAD);
  expect(state().wedgeReading).toBe(true);
  await act(async () => actions().toggleManual());
  expect(state().wedgeReading).toBe(false);
  await act(async () => actions().setField("full_name", "Manual Name"));
  await act(async () => decode.resolve({ data: { outcome: "card", data: CARD } }));
  expect(state().form.full_name).toBe("Manual Name");
  expect(state().qrPayload).toBe("");
  expect(state().locked("full_name")).toBe(false);
});

test("a decode that lands after the modal closed changes nothing", async () => {
  await mount();
  const decode = deferred();
  routes({ "/aadhaar/decode": () => decode.promise });
  await fireBurst(PAYLOAD);
  await update({ open: false });
  await act(async () => decode.resolve({ data: { outcome: "card", data: CARD } }));
  expect(state().qrPayload).toBe("");
  expect(state().form.full_name).toBe("");
});

test("a decode that lands in time fills the form and stops the reading status", async () => {
  await mount();
  const decode = deferred();
  routes({ "/aadhaar/decode": () => decode.promise });
  await fireBurst(PAYLOAD);
  expect(state().wedgeReading).toBe(true);
  await act(async () => decode.resolve({ data: { outcome: "card", data: CARD } }));
  expect(state().wedgeReading).toBe(false);
  expect(state().form.full_name).toBe("Sunita Devi");
  expect(state().locked("full_name")).toBe(true);
});

test("a decode that fails shows the failure", async () => {
  await mount();
  routes({ "/aadhaar/decode": lost });
  await fireBurst(PAYLOAD);
  expect(state().error).toBe("Network Error");
  expect(state().wedgeReading).toBe(false);
});

test("a cut-off USB burst says so", async () => {
  await mount();
  let t = Number(performance.now()) || 0;
  const spy = jest.spyOn(performance, "now").mockImplementation(() => t);
  await act(async () => {
    for (const ch of PAYLOAD.slice(0, 30)) {
      t += 10;
      document.dispatchEvent(new KeyboardEvent("keydown", { key: ch, bubbles: true, cancelable: true }));
    }
    t += 10;
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true, cancelable: true }));
  });
  spy.mockRestore();
  expect(state().error).toBe("The USB scan was cut off. Scan the card again.");
});

test("the door does not listen for USB bursts", async () => {
  routes({ "/aadhaar/decode": decodesCard });
  await mount({ atDoor: true });
  await fireBurst(PAYLOAD);
  expect(api.post).not.toHaveBeenCalled();
});

test("the desk listens for USB bursts only out of manual mode and while nothing is saving", async () => {
  routes({ "/aadhaar/decode": decodesCard, "/register": () => new Promise(() => {}) });
  await mount();
  await act(async () => actions().toggleManual());
  await fireBurst(PAYLOAD);
  expect(api.post).not.toHaveBeenCalled();
  await act(async () => actions().toggleManual());
  await scan();
  act(() => { actions().save(); });
  expect(state().busy).toBe(true);
  api.post.mockClear();
  await fireBurst(PAYLOAD);
  expect(api.post).not.toHaveBeenCalled();
});

test("opening with an initialPayload reads the card and fills the form", async () => {
  routes({ "/aadhaar/decode": decodesCard });
  await mount({ open: false });
  await update({ open: true, initialPayload: PAYLOAD });
  expect(api.post.mock.calls.filter(([url]) => url === "/aadhaar/decode")).toHaveLength(1);
  expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", { payload: PAYLOAD });
  expect(state().form.full_name).toBe("Sunita Devi");
  expect(state().qrPayload).toBe(PAYLOAD);
  expect(state().wedgeReading).toBe(false);
});

test("a form already open when its initialPayload arrives reads the card once", async () => {
  routes({ "/aadhaar/decode": decodesCard });
  await mount();
  await update({ initialPayload: PAYLOAD });
  await update({ days: [...DAYS] });
  expect(api.post.mock.calls.filter(([url]) => url === "/aadhaar/decode")).toHaveLength(1);
  expect(state().qrPayload).toBe(PAYLOAD);
});

test("two saves in the same tick send one request", async () => {
  await mount();
  const reply = deferred();
  routes({ "/register": () => reply.promise });
  await scan();
  let both;
  await act(async () => { both = Promise.all([actions().save(), actions().save()]); });
  expect(registers()).toHaveLength(1);
  expect(state().busy).toBe(true);
  await act(async () => { reply.resolve({ data: { registration: REG } }); await both; });
  expect(props.onDone).toHaveBeenCalledTimes(1);
});

test("a save that cannot be submitted sends nothing", async () => {
  await mount();
  routes({ "/register": registered });
  await act(async () => actions().onScanned(CARD, PAYLOAD));
  await save();
  expect(api.post).not.toHaveBeenCalled();
  expect(state().busy).toBe(false);
});

test("a saved registration at the desk says the SMS went out, tells the desk and closes", async () => {
  await mount();
  routes({ "/register": registered });
  await scan();
  await save();
  expect(props.setBanner).toHaveBeenCalledWith("Registered #107 — Sunita Devi. SMS sent.");
  expect(props.onRegistered).toHaveBeenCalledTimes(1);
  expect(props.onRegistered).toHaveBeenCalledWith(REG);
  expect(props.onDone).toHaveBeenCalledTimes(1);
  expect(props.onDone).toHaveBeenCalledWith({ registration: REG, created: true });
  expect(props.onClose).toHaveBeenCalledTimes(1);
  expect(state().busy).toBe(false);
});

test("a saved registration at the door books the operating day and says it arrived", async () => {
  await mount({ atDoor: true });
  routes({ "/register": registered });
  expect(state().manualMode).toBe(true);
  await act(async () => actions().chooseReason({ code: "no_card", note: "" }));
  await act(async () => {
    actions().setField("gender", "F");
    actions().setField("full_name", "Kamla Bai");
    actions().setField("age", "62");
    actions().setField("phone", "9876500002");
  });
  await save();
  expect(registers()[0]).toEqual(expect.objectContaining({ camp_day_id: "day-9", at_door: true, manual_reason: "no_card" }));
  expect(props.setBanner).toHaveBeenCalledWith("Registered and arrived: #107 — Sunita Devi");
  expect(props.onClose).toHaveBeenCalledTimes(1);
});

test("Register and next opens the next patient instead of closing, and keeps the chosen day", async () => {
  await mount();
  routes({ "/register": registered });
  await act(async () => actions().chooseDay("day-2"));
  await scan();
  await save({ next: true });
  expect(props.onClose).not.toHaveBeenCalled();
  expect(props.onDone).toHaveBeenCalledTimes(1);
  expect(state().dayId).toBe("day-2");
  expect(state().qrPayload).toBe("");
  await scan();
  await save({ next: true });
  expect(registers()[1].camp_day_id).toBe("day-2");
});

test("the chosen day defaults to today and follows the days that arrive", async () => {
  await mount({ days: [] });
  expect(state().dayId).toBe("");
  await update({ days: DAYS });
  expect(state().dayId).toBe("day-1");
  expect(state().bookedDay).toBe("day-1");
});

test("a failed save shows its error and leaves the form to fix", async () => {
  await mount();
  routes({ "/register": () => Promise.reject(refusal({ code: "DUPLICATE_IN_CAMP", registration: { reg_no: 7 } })) });
  await scan();
  await save();
  expect(state().error).toBe("Already registered as #7. Find them below and print.");
  expect(state().busy).toBe(false);
  expect(state().qrPayload).toBe(PAYLOAD);
  expect(props.onClose).not.toHaveBeenCalled();
  expect(props.onDone).not.toHaveBeenCalled();
});

test.each([false, true])("a save that lands after Cancel and reopen leaves the new form and modal alone (next: %s)", async (next) => {
  await mount();
  const reply = deferred();
  routes({ "/register": () => reply.promise });
  await scan();
  let saving;
  await act(async () => { saving = actions().save({ next }); });
  await update({ open: false });
  await update({ open: true });
  await act(async () => actions().setField("full_name", "New Patient"));
  await act(async () => { reply.resolve({ data: { registration: REG, created: true } }); await saving; });
  expect(props.onClose).not.toHaveBeenCalled();
  expect(props.onDone).toHaveBeenCalledTimes(1);
  expect(props.setBanner).toHaveBeenCalledTimes(1);
  expect(state().form.full_name).toBe("New Patient");
  expect(state().busy).toBe(false);
});

test("a failed save that lands after Cancel and reopen writes nothing into the new form", async () => {
  await mount();
  const reply = deferred();
  routes({ "/register": () => reply.promise });
  await act(async () => actions().toggleManual());
  await act(async () => actions().chooseReason({ code: "no_card", note: "" }));
  await act(async () => {
    actions().setField("gender", "F");
    actions().setField("full_name", "Ram Kumar");
    actions().setField("age", "40");
    actions().setField("phone", "9876500001");
  });
  let saving;
  await act(async () => { saving = actions().save(); });
  await update({ open: false });
  await update({ open: true });
  const lookalikes = { code: "LOOKALIKES", registrations: [{ id: "p-3", reg_no: "103" }] };
  await act(async () => { reply.reject(refusal(lookalikes)); await saving; });
  expect(state().lookalikeRows).toBeNull();
  expect(state().review).toBeNull();
  expect(state().error).toBe("");
  expect(state().busy).toBe(false);
});

test("the actions keep their identity across renders", async () => {
  await mount();
  const before = actions();
  await update({ days: [...DAYS] });
  expect(actions()).toBe(before);
});

test("captureStarted drops the card and keeps the typed phone", async () => {
  await mount();
  await scan("9876500001");
  await act(async () => actions().captureStarted());
  expect(state().qrPayload).toBe("");
  expect(state().form.phone).toBe("9876500001");
  expect(state().form.full_name).toBe("");
});
