import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { useRegistrationRequest } from "./useRegistrationRequest";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;
let request;

function Harness() {
  request = useRegistrationRequest();
  return null;
}

const refusal = (code) => ({ response: { status: 409, data: { detail: { code, message: `Refused: ${code}` } } } });

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function attempts() {
  const used = [];
  const post = (outcome) => (id) => {
    used.push(id);
    return outcome instanceof Error || outcome?.response ? Promise.reject(outcome) : Promise.resolve(outcome);
  };
  return { used, post };
}

async function send(payload, post) {
  let outcome;
  await act(async () => {
    outcome = await request.send(payload, post).then((data) => ({ data }), (failure) => ({ failure }));
  });
  return outcome;
}

beforeEach(async () => {
  container = document.createElement("div");
  root = ReactDOM.createRoot(container);
  await act(async () => root.render(<Harness />));
});

afterEach(() => {
  act(() => root.unmount());
});

test("the same payload resends the same id until a send succeeds", async () => {
  const { used, post } = attempts();
  const lost = post(new Error("Network Error"));
  await send({ phone: "1" }, lost);
  await send({ phone: "1" }, lost);
  expect(used[1]).toBe(used[0]);
  expect(used[0]).toEqual(expect.any(String));
});

test("a changed payload gets a new id, and going back does not resurrect the old one", async () => {
  const { used, post } = attempts();
  const lost = post(new Error("Network Error"));
  await send({ phone: "1" }, lost);
  await send({ phone: "2" }, lost);
  await send({ phone: "1" }, lost);
  expect(used[1]).not.toBe(used[0]);
  expect(used[2]).not.toBe(used[0]);
  expect(used[2]).not.toBe(used[1]);
});

test("a payload is compared by value, not identity", async () => {
  const { used, post } = attempts();
  const lost = post(new Error("Network Error"));
  await send({ a: 1, b: [2] }, lost);
  await send({ a: 1, b: [2] }, lost);
  expect(used[1]).toBe(used[0]);
});

test("success clears the id so the next send is a new registration", async () => {
  const { used, post } = attempts();
  await send({ phone: "1" }, post({ data: {} }));
  await send({ phone: "1" }, post({ data: {} }));
  expect(used[1]).not.toBe(used[0]);
});

test("a registration request conflict clears the id", async () => {
  const { used, post } = attempts();
  const { failure } = await send({ phone: "1" }, post(refusal("REGISTRATION_REQUEST_CONFLICT")));
  expect(failure.response.data.detail.code).toBe("REGISTRATION_REQUEST_CONFLICT");
  await send({ phone: "1" }, post(new Error("Network Error")));
  expect(used[1]).not.toBe(used[0]);
});

test("reset clears the id", async () => {
  const { used, post } = attempts();
  const lost = post(new Error("Network Error"));
  await send({ phone: "1" }, lost);
  act(() => request.reset());
  await send({ phone: "1" }, lost);
  expect(used[1]).not.toBe(used[0]);
});

test.each([
  ["a network error", new Error("Network Error")],
  ["a validation refusal", { response: { status: 422, data: { detail: "Invalid phone" } } }],
  ["MISMATCH_REVIEW_REQUIRED", refusal("MISMATCH_REVIEW_REQUIRED")],
  ["LOOKALIKES", refusal("LOOKALIKES")],
  ["DUPLICATE_IN_CAMP", refusal("DUPLICATE_IN_CAMP")],
  ["CAMP_REQUEST_CONFLICT", refusal("CAMP_REQUEST_CONFLICT")],
])("%s keeps the id", async (_name, failure) => {
  const { used, post } = attempts();
  const refused = post(failure);
  await send({ phone: "1" }, refused);
  await send({ phone: "1" }, refused);
  expect(used[1]).toBe(used[0]);
});

test("errors reach the caller unchanged", async () => {
  const failure = refusal("LOOKALIKES");
  const outcome = await send({ phone: "1" }, () => Promise.reject(failure));
  expect(outcome.failure).toBe(failure);
});

test("a result reaches the caller unchanged", async () => {
  const reply = { data: { registration: { id: "p-1" } } };
  const outcome = await send({ phone: "1" }, () => Promise.resolve(reply));
  expect(outcome.data).toBe(reply);
});

test("a late reply never clears a newer payload's id", async () => {
  const { used, post } = attempts();
  const first = deferred();
  const lost = post(new Error("Network Error"));
  let pending;
  await act(async () => {
    pending = request.send({ phone: "1" }, (id) => { used.push(id); return first.promise; });
  });
  await send({ phone: "2" }, lost);
  await act(async () => { first.resolve({ data: {} }); await pending; });
  await send({ phone: "2" }, lost);
  expect(used[1]).not.toBe(used[0]);
  expect(used[2]).toBe(used[1]);
});

test("a late conflict never clears a newer payload's id", async () => {
  const { used, post } = attempts();
  const first = deferred();
  const lost = post(new Error("Network Error"));
  let pending;
  await act(async () => {
    pending = request.send({ phone: "1" }, (id) => { used.push(id); return first.promise; }).catch(() => {});
  });
  await send({ phone: "2" }, lost);
  await act(async () => { first.reject(refusal("REGISTRATION_REQUEST_CONFLICT")); await pending; });
  await send({ phone: "2" }, lost);
  expect(used[2]).toBe(used[1]);
});

test("send and reset keep their identity across renders", async () => {
  const before = request;
  await act(async () => root.render(<Harness />));
  expect(request).toBe(before);
});
