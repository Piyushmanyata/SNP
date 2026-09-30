import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { TemplateLogosEditor } from "./TemplateLogosEditor";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

test("Add logo stays in the tab order and shows the emerald focus ring", () => {
  act(() =>
    root.render(<TemplateLogosEditor logos={[]} onAddLogo={() => {}} onMoveLogo={() => {}} onRemoveLogo={() => {}} />),
  );
  const input = container.querySelector('[data-testid="tpl-logo-input"]');
  const label = container.querySelector('[data-testid="tpl-add-logo-label"]');
  expect(input.classList).not.toContain("hidden");
  expect(input.classList).toContain("sr-only");
  expect(input.disabled).toBe(false);
  for (const cls of ["focus-within:ring-2", "focus-within:ring-emerald-500", "focus-within:ring-offset-2", "min-h-[44px]"]) {
    expect(label.classList).toContain(cls);
  }
});
