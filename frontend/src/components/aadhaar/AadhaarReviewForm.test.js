import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { AadhaarReviewForm } from "./AadhaarReviewForm";

global.IS_REACT_ACT_ENVIRONMENT = true;

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
