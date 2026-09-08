import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { AadhaarReviewForm, ageFromDob } from "./AadhaarReviewForm";

global.IS_REACT_ACT_ENVIRONMENT = true;

function setValue(input, value) {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

test("ageFromDob reads a full date, a bare year and nothing else", () => {
  const year = new Date().getFullYear();
  expect(ageFromDob(`${year - 40}-01-01`)).toBe("40");
  expect(ageFromDob(`${year - 40}`)).toBe("40");
  expect(ageFromDob(`${year + 1}-01-01`)).toBe("");
  expect(ageFromDob("1975-02-30")).toBe("");
  expect(ageFromDob("14/06/1975")).toBe("");
  expect(ageFromDob("")).toBe("");
  expect(ageFromDob(undefined)).toBe("");
});

test("a transcribed birth date fills the age and follows corrections to it", () => {
  const year = new Date().getFullYear();
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(<AadhaarReviewForm initial={{ full_name: "Sunita Devi", dob: `${year - 51}-01-01` }} onConfirm={jest.fn()} />));
  const age = container.querySelector('[data-testid="aadhaar-review-age"]');
  expect(age.value).toBe("51");
  act(() => setValue(container.querySelector('[data-testid="aadhaar-review-dob"]'), `${year - 30}`));
  expect(age.value).toBe("30");
  act(() => setValue(container.querySelector('[data-testid="aadhaar-review-dob"]'), "not-a-date"));
  expect(age.value).toBe("30");
  act(() => root.unmount());
  container.remove();
});

test("transcribed details require review and allow corrections before use", () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const onConfirm = jest.fn();
  act(() => root.render(<AadhaarReviewForm initial={{ full_name: "Sunlta", age: 51, aadhaar_last4: "1234" }} onConfirm={onConfirm} />));
  const button = container.querySelector('[data-testid="aadhaar-review-confirm"]');
  expect(button.disabled).toBe(true);
  const name = container.querySelector('[data-testid="aadhaar-review-full_name"]');
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(name, "Sunita Devi");
    name.dispatchEvent(new Event("input", { bubbles: true }));
    container.querySelector('[data-testid="aadhaar-review-check"]').click();
  });
  act(() => button.click());
  expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ full_name: "Sunita Devi", age: "51", aadhaar_last4: "1234" }));
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(name, "Different Patient");
    name.dispatchEvent(new Event("input", { bubbles: true }));
  });
  expect(button.disabled).toBe(true);
  act(() => root.unmount());
  container.remove();
});
